"""Building service utilities for handling upgrades and queues."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Dict, List

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..utils import utc_now
from . import achievement as achievement_service
from . import notification as notification_service
from . import premium as premium_service
from . import production, quest as quest_service, ranking

logger = logging.getLogger(__name__)
BUILDING_COSTS: Dict[str, Dict[str, float]] = {
    "town_hall": {"wood": 260, "clay": 200, "iron": 150},
    "barracks": {"wood": 200, "clay": 160, "iron": 170},
    "stable": {"wood": 320, "clay": 260, "iron": 260},
    "wall": {"wood": 100, "clay": 100, "iron": 50},
    "market": {"wood": 100, "clay": 100, "iron": 100},
    "farm": {"wood": 80, "clay": 80, "iron": 60},
    "warehouse": {"wood": 130, "clay": 100, "iron": 90},
    "smithy": {"wood": 220, "clay": 180, "iron": 240},
    "workshop": {"wood": 460, "clay": 510, "iron": 600},
    "world_wonder": {"wood": 10000, "clay": 10000, "iron": 10000},
}

BUILDING_PREREQUISITES: Dict[str, Dict[str, int]] = {
    "stable": {"barracks": 5, "town_hall": 3},
    "market": {"warehouse": 1, "town_hall": 2},
    "wall": {"barracks": 1},
    "smithy": {"town_hall": 5, "barracks": 1},
    "workshop": {"town_hall": 10, "stable": 10},
    "world_wonder": {"town_hall": 20, "warehouse": 20},
}

BASE_BUILD_TIME_SECONDS = 420
REFUND_FACTOR = 0.8


@lru_cache(maxsize=1)
def get_building_costs() -> Dict[str, Dict[str, float]]:
    """Return cached building cost definitions."""

    return BUILDING_COSTS


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def calculate_upgrade_cost(building_name: str, target_level: int) -> Dict[str, float]:
    """Return the canonical cost for reaching ``target_level``.

    Both the quote endpoint and the payment path call this exact function. The
    target level is explicit so a current-level object cannot accidentally be
    interpreted as either the source or destination level.
    """

    if target_level < 1:
        raise ValueError("Target building level must be at least 1")
    base = get_building_costs().get(building_name)
    if base is None:
        raise ValueError(f"Unknown building type: {building_name}")
    multiplier = 1.2 ** (target_level - 1)
    return {resource: float(value * multiplier) for resource, value in base.items()}


def calculate_build_time(target_level: int) -> int:
    if target_level < 1:
        raise ValueError("Target building level must be at least 1")
    return BASE_BUILD_TIME_SECONDS * target_level


def get_available_buildings(db: Session, city: models.City) -> List[dict]:
    """Return server-authoritative quotes for every supported building."""

    existing_map = {building.name: building for building in city.buildings}
    result = []

    for name in BUILDING_COSTS:
        building = existing_map.get(name)
        current_level = building.level if building else 0
        target_level = current_level + 1
        cost = calculate_upgrade_cost(name, target_level)

        prereqs = BUILDING_PREREQUISITES.get(name, {})
        requirements_met = all(
            existing_map.get(req_name) is not None
            and existing_map[req_name].level >= req_level
            for req_name, req_level in prereqs.items()
        )

        result.append(
            {
                "name": name,
                "level": current_level,
                "cost": cost,
                "requirements_met": requirements_met,
                "requirements": prereqs,
                "build_time": calculate_build_time(target_level),
            }
        )

    return result


def queue_upgrade(db: Session, city: models.City, building_name: str) -> models.BuildingQueue:
    """Quote, pay and queue one building target level atomically."""

    if building_name not in BUILDING_COSTS:
        raise ValueError(f"Unknown building type: {building_name}")

    # Premium status may need to be created before the city resource lock.
    status = premium_service.get_or_create_status(db, city.owner)

    city, production_gains = production.lock_and_recalculate_resources(db, city)
    db.expire(city, ["buildings"])

    existing_queue = (
        db.query(models.BuildingQueue)
        .filter(models.BuildingQueue.city_id == city.id)
        .count()
    )
    allowed_slots = premium_service.get_build_queue_limit(status)
    if existing_queue >= allowed_slots:
        db.rollback()
        raise ValueError("No building queue slots available")

    already_queued = (
        db.query(models.BuildingQueue)
        .filter(
            models.BuildingQueue.city_id == city.id,
            models.BuildingQueue.building_type == building_name,
        )
        .first()
    )
    if already_queued:
        db.rollback()
        raise ValueError("Building upgrade already queued")

    prereqs = BUILDING_PREREQUISITES.get(building_name, {})
    if prereqs:
        existing_buildings = {b.name: b.level for b in city.buildings}
        for req_name, req_level in prereqs.items():
            if existing_buildings.get(req_name, 0) < req_level:
                db.rollback()
                raise ValueError(
                    f"Prerequisite not met: {req_name} level {req_level} required"
                )

    building = (
        db.query(models.Building)
        .options(selectinload(models.Building.city))
        .filter(
            models.Building.city_id == city.id,
            models.Building.name == building_name,
        )
        .first()
    )
    if not building:
        building = models.Building(city_id=city.id, name=building_name, level=0)
        db.add(building)
        db.flush()

    target_level = building.level + 1
    cost = calculate_upgrade_cost(building_name, target_level)
    if not production.check_cost(city, cost):
        db.rollback()
        raise ValueError("Insufficient resources")

    production.pay_cost(city, cost)

    finish_time = utc_now() + timedelta(seconds=calculate_build_time(target_level))
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type=building_name,
        target_level=target_level,
        finish_time=finish_time,
        paid_cost={resource: float(amount) for resource, amount in cost.items()},
    )
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)

    production.record_resource_gains(db, city, production_gains)
    logger.info(
        "building_upgrade_queued",
        extra={
            "city_id": city.id,
            "building": building_name,
            "target_level": target_level,
            "paid_cost": queue_entry.paid_cost,
            "finish_time": finish_time.isoformat(),
        },
    )
    return queue_entry


def _run_completion_side_effects(db: Session, info: dict) -> None:
    """Run non-authoritative progress/notification effects after queue commit.

    The queue row has already been deleted before any helper here can commit.
    This prevents a concurrent processor from observing the same due queue after
    quest/achievement services release the transaction lock.
    """

    owner_id = info.get("owner_id")
    world_id = info.get("world_id")
    if not owner_id or not world_id:
        return

    user = db.query(models.User).filter(models.User.id == owner_id).first()
    if not user:
        return

    try:
        quest_service.handle_event(
            db,
            user,
            "building_finished",
            {
                "building_type": info["building_type"],
                "level": info["target_level"],
            },
        )
        achievement_service.update_achievement_progress(
            db,
            owner_id,
            "build_level",
            absolute_value=info["target_level"],
        )
        ranking.recalculate_player_and_alliance_scores(db, owner_id, world_id)
        if info.get("world_won"):
            notification_service.create_notification(
                db,
                user,
                title="¡Victoria!",
                body="¡Has completado la Maravilla del Mundo y ganado el servidor!",
                notification_type="world_won",
            )
    except Exception:
        db.rollback()
        logger.exception(
            "building_completion_side_effect_failed",
            extra={
                "city_id": info["city_id"],
                "building": info["building_type"],
                "target_level": info["target_level"],
            },
        )


def process_building_queues(db: Session) -> List[dict]:
    """Finalize each due queue at most once across concurrent processors."""

    now = utc_now()
    finished_queues = (
        db.query(models.BuildingQueue)
        .filter(models.BuildingQueue.finish_time <= now)
        .options(selectinload(models.BuildingQueue.city))
        .order_by(models.BuildingQueue.id.asc())
        .with_for_update(skip_locked=True)
        .all()
    )
    if not finished_queues:
        return []

    finished_info: List[dict] = []
    for queue_entry in finished_queues:
        city = queue_entry.city
        if city is None:
            logger.error(
                "building_queue_missing_city",
                extra={"queue_id": queue_entry.id, "city_id": queue_entry.city_id},
            )
            db.delete(queue_entry)
            continue

        building = (
            db.query(models.Building)
            .filter(
                models.Building.city_id == queue_entry.city_id,
                models.Building.name == queue_entry.building_type,
            )
            .with_for_update()
            .one_or_none()
        )
        if building is None:
            building = models.Building(
                city_id=queue_entry.city_id,
                name=queue_entry.building_type,
                level=0,
            )
            db.add(building)
            db.flush()

        building.level = max(building.level, queue_entry.target_level)
        world_won = False
        if building.name == "world_wonder" and building.level >= 100:
            world = (
                db.query(models.World)
                .filter(models.World.id == city.world_id)
                .with_for_update()
                .one_or_none()
            )
            if world and world.is_active:
                world.is_active = False
                world.ended_at = now
                world.winner_id = city.owner_id
                world_won = True

        finished_info.append(
            {
                "city_id": queue_entry.city_id,
                "building_type": queue_entry.building_type,
                "target_level": queue_entry.target_level,
                "owner_id": city.owner_id,
                "world_id": city.world_id,
                "world_won": world_won,
            }
        )
        db.delete(queue_entry)

    # The authoritative mutation and queue deletion happen before helpers that
    # perform their own commits. Once this commit succeeds, another processor
    # cannot ever finish these queue rows again.
    db.commit()

    for info in finished_info:
        _run_completion_side_effects(db, info)

    if finished_info:
        logger.info(
            "building_queues_completed",
            extra={
                "count": len(finished_info),
                "cities": [item["city_id"] for item in finished_info],
            },
        )

    return [
        {
            "city_id": info["city_id"],
            "building_type": info["building_type"],
            "target_level": info["target_level"],
        }
        for info in finished_info
    ]


def cancel_building_queue(db: Session, queue_id: int, user_id: int) -> bool:
    """Cancel a future queue and refund 80% of the exact recorded payment."""

    queue_entry = (
        db.query(models.BuildingQueue)
        .join(models.City)
        .filter(
            models.BuildingQueue.id == queue_id,
            models.City.owner_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if not queue_entry:
        return False

    if _as_utc(queue_entry.finish_time) <= _as_utc(utc_now()):
        db.rollback()
        raise ValueError("Completed building queue can no longer be cancelled")

    city, production_gains = production.lock_and_recalculate_resources(
        db, queue_entry.city_id
    )

    paid_cost = queue_entry.paid_cost or calculate_upgrade_cost(
        queue_entry.building_type,
        queue_entry.target_level,
    )
    refund = {
        resource: float(amount) * REFUND_FACTOR
        for resource, amount in paid_cost.items()
    }

    storage_limit = production.get_storage_limit(city)
    for resource, amount in refund.items():
        current_value = float(getattr(city, resource))
        if current_value >= storage_limit:
            continue
        setattr(city, resource, min(current_value + amount, storage_limit))

    db.delete(queue_entry)
    db.commit()
    production.record_resource_gains(db, city, production_gains)
    logger.info(
        "building_upgrade_cancelled",
        extra={
            "city_id": city.id,
            "building": queue_entry.building_type,
            "target_level": queue_entry.target_level,
            "refund": refund,
        },
    )
    return True
