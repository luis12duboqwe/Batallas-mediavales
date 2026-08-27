"""Troop training and queue management services."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..utils import utc_now
from . import achievement as achievement_service
from . import balance
from . import event as event_service
from . import premium as premium_service
from . import production, quest as quest_service, ranking, research as research_service
from . import unit_catalog, world_lifecycle

logger = logging.getLogger(__name__)
REFUND_FACTOR = balance.QUEUE_REFUND_FACTOR

# Compatibility views for older callers. They are generated from one source of
# truth instead of carrying separate balance tables in this module.
UNIT_REQUIREMENTS: Dict[str, Dict[str, int]] = {
    unit_type: unit_catalog.get_unit(unit_type)["training_requirements"]
    for unit_type in unit_catalog.UNIT_ORDER
}


def get_unit_costs() -> Dict[str, Dict[str, float]]:
    return {
        unit_type: unit_catalog.get_unit(unit_type)["training_cost"]
        for unit_type in unit_catalog.UNIT_ORDER
    }


def get_training_times() -> Dict[str, int]:
    return {
        unit_type: int(unit_catalog.get_unit(unit_type)["training_time_seconds"])
        for unit_type in unit_catalog.UNIT_ORDER
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def check_requirements(city: models.City, unit_type: str) -> None:
    definition = unit_catalog.get_unit(unit_type)
    missing = unit_catalog.first_missing_requirement(
        city, definition["training_requirements"]
    )
    if missing:
        building_name, level = missing
        raise ValueError(f"Requirement not met: {building_name} level {level}")

    db = Session.object_session(city)
    if db is None:
        raise ValueError("City is not attached to a database session")
    if not unit_catalog.is_researched(db, city.id, unit_type):
        raise ValueError(f"Unit {unit_type} not researched")


def research_unit(db: Session, city: models.City, unit_type: str):
    return research_service.research_tech(db, city, unit_type)


def queue_training(
    db: Session, city: models.City, unit_type: str, quantity: int
) -> models.TroopQueue:
    """Quote, reserve population/upkeep, pay and queue training atomically."""

    world_lifecycle.require_world_open(db, city.world_id)

    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    definition = unit_catalog.get_unit(unit_type)

    status = premium_service.get_or_create_status(db, city.owner)
    city, production_gains = production.lock_and_recalculate_resources(db, city)
    db.expire(city, ["buildings"])

    existing_queue = (
        db.query(models.TroopQueue)
        .filter(models.TroopQueue.city_id == city.id)
        .count()
    )
    allowed_slots = premium_service.get_troop_queue_limit(status)
    if existing_queue >= allowed_slots:
        db.rollback()
        raise ValueError("No troop training queue slots available")

    try:
        check_requirements(city, unit_type)
    except Exception:
        db.rollback()
        raise

    if not unit_catalog.has_population_capacity(db, city, unit_type, quantity):
        db.rollback()
        raise ValueError("Not enough population capacity")

    # The city row is still locked here. Because active training queues reserve
    # their future upkeep, concurrent requests for the same city serialize on
    # this check and cannot both consume the same sustainable gold headroom.
    if not unit_catalog.has_upkeep_capacity(db, city, unit_type, quantity):
        db.rollback()
        raise ValueError("Not enough sustainable gold income for troop upkeep")

    total_cost = {
        resource: float(cost) * quantity
        for resource, cost in definition["training_cost"].items()
    }
    if not production.check_cost(city, total_cost):
        db.rollback()
        raise ValueError("Insufficient resources")

    production.pay_cost(city, total_cost)

    modifiers = event_service.get_active_modifiers(db, world_id=city.world_id)
    training_time_multiplier = float(modifiers.get("troop_training_speed", 1.0))
    if training_time_multiplier <= 0:
        db.rollback()
        raise ValueError("Invalid troop training speed modifier")
    duration_seconds = (
        float(definition["training_time_seconds"])
        * quantity
        * training_time_multiplier
    )
    finish_time = utc_now() + timedelta(seconds=duration_seconds)

    queue_entry = models.TroopQueue(
        city_id=city.id,
        troop_type=unit_type,
        amount=quantity,
        finish_time=finish_time,
        paid_cost={resource: float(amount) for resource, amount in total_cost.items()},
    )
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    production.record_resource_gains(db, city, production_gains)

    logger.info(
        "troop_training_queued",
        extra={
            "city_id": city.id,
            "unit_type": unit_type,
            "quantity": quantity,
            "paid_cost": queue_entry.paid_cost,
            "finish_time": finish_time.isoformat(),
            "upkeep_per_hour": float(definition.get("upkeep_per_hour", 0.0)) * quantity,
        },
    )
    return queue_entry


def _run_training_side_effects(db: Session, info: dict) -> None:
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
            "troops_trained",
            {"unit_type": info["troop_type"], "amount": info["amount"]},
        )
        achievement_service.update_achievement_progress(
            db,
            owner_id,
            "train_troops",
            world_id=world_id,
            increment=info["amount"],
        )
        ranking.recalculate_player_and_alliance_scores(db, owner_id, world_id)
    except Exception:
        db.rollback()
        logger.exception(
            "troop_training_side_effect_failed",
            extra={
                "city_id": info["city_id"],
                "unit_type": info["troop_type"],
                "amount": info["amount"],
            },
        )


def process_troop_queues(db: Session) -> List[dict]:
    """Process each completed training queue at most once."""

    now = utc_now()
    finished_queues = (
        db.query(models.TroopQueue)
        .filter(
            models.TroopQueue.finish_time <= now,
            models.TroopQueue.city_id.in_(
                db.query(models.City.id).filter(
                    models.City.world_id.in_(
                        db.query(models.World.id).filter(models.World.lifecycle_status == "open")
                    )
                )
            ),
        )
        .options(selectinload(models.TroopQueue.city))
        .order_by(models.TroopQueue.id.asc())
        .with_for_update(skip_locked=True)
        .all()
    )
    if not finished_queues:
        return []

    internal_info: List[dict] = []
    for queue_entry in finished_queues:
        city = queue_entry.city
        if city is None:
            logger.error(
                "troop_queue_missing_city",
                extra={"queue_id": queue_entry.id, "city_id": queue_entry.city_id},
            )
            db.delete(queue_entry)
            continue

        troop = (
            db.query(models.Troop)
            .filter(
                models.Troop.city_id == queue_entry.city_id,
                models.Troop.unit_type == queue_entry.troop_type,
            )
            .with_for_update()
            .one_or_none()
        )
        if troop is None:
            troop = models.Troop(
                city_id=queue_entry.city_id,
                unit_type=queue_entry.troop_type,
                quantity=0,
            )
            db.add(troop)
            db.flush()

        troop.quantity += queue_entry.amount
        internal_info.append(
            {
                "city_id": queue_entry.city_id,
                "troop_type": queue_entry.troop_type,
                "amount": queue_entry.amount,
                "owner_id": city.owner_id,
                "world_id": city.world_id,
            }
        )
        db.delete(queue_entry)

    db.commit()

    for info in internal_info:
        _run_training_side_effects(db, info)

    logger.info(
        "troop_training_completed",
        extra={
            "count": len(internal_info),
            "cities": [item["city_id"] for item in internal_info],
        },
    )
    return [
        {
            "city_id": info["city_id"],
            "troop_type": info["troop_type"],
            "amount": info["amount"],
        }
        for info in internal_info
    ]


def cancel_troop_queue(db: Session, queue_id: int, user_id: int) -> bool:
    """Cancel future training and refund the canonical queue refund factor."""

    queue_entry = (
        db.query(models.TroopQueue)
        .join(models.City)
        .filter(
            models.TroopQueue.id == queue_id,
            models.City.owner_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if not queue_entry:
        return False

    queue_city = db.query(models.City).filter(models.City.id == queue_entry.city_id).one()
    world_lifecycle.require_world_open(db, queue_city.world_id)

    if _as_utc(queue_entry.finish_time) <= _as_utc(utc_now()):
        db.rollback()
        raise ValueError("Completed troop queue can no longer be cancelled")

    city, production_gains = production.lock_and_recalculate_resources(
        db, queue_entry.city_id
    )

    if queue_entry.paid_cost:
        paid_cost = {
            resource: float(amount)
            for resource, amount in queue_entry.paid_cost.items()
        }
    else:
        definition = unit_catalog.get_unit(queue_entry.troop_type)
        paid_cost = {
            resource: float(cost) * queue_entry.amount
            for resource, cost in definition["training_cost"].items()
        }

    refund = {
        resource: amount * REFUND_FACTOR
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
    return True
