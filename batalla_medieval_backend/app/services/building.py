"""Building service utilities for handling upgrades and queues."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List

from sqlalchemy.orm import Session, selectinload

from .. import models
from . import premium as premium_service
from . import production, quest as quest_service, ranking

logger = logging.getLogger(__name__)
BUILDING_COSTS: Dict[str, Dict[str, float]] = {
    "town_hall": {"wood": 260, "clay": 200, "iron": 150},
    "barracks": {"wood": 200, "clay": 160, "iron": 170},
    "stable": {"wood": 320, "clay": 260, "iron": 260},
}

BASE_BUILD_TIME_SECONDS = 420


@lru_cache(maxsize=1)
def get_building_costs() -> Dict[str, Dict[str, float]]:
    """Return cached building cost definitions."""

    return {
        "town_hall": {"wood": 200, "clay": 150, "iron": 100},
        "barracks": {"wood": 150, "clay": 150, "iron": 120},
        "stable": {"wood": 250, "clay": 200, "iron": 200},
    }


def queue_upgrade(db: Session, city: models.City, building_name: str) -> models.BuildingQueue:
    """Queue an upgrade for a building, enforcing premium limits and costs."""

    status = premium_service.get_or_create_status(db, city.owner)
    existing_queue = (
        db.query(models.BuildingQueue)
        .filter(models.BuildingQueue.city_id == city.id)
        .count()
    )
    allowed_slots = premium_service.get_build_queue_limit(status)
    if existing_queue >= allowed_slots:
        raise ValueError("No building queue slots available")

    building = (
        db.query(models.Building)
        .options(selectinload(models.Building.city))
        .filter(models.Building.city_id == city.id, models.Building.name == building_name)
        .first()
    )
    if not building:
        building = models.Building(city_id=city.id, name=building_name, level=0)
        db.add(building)
        db.commit()
        db.refresh(building)

    cost = calculate_upgrade_cost(building)
    production.recalculate_resources(db, city)
    production.pay_cost(city, cost)

    target_level = building.level + 1
    duration_seconds = BASE_BUILD_TIME_SECONDS * target_level
    finish_time = datetime.utcnow() + timedelta(seconds=duration_seconds)

    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type=building_name,
        target_level=target_level,
        finish_time=finish_time,
    )
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    ranking.recalculate_player_and_alliance_scores(db, city.owner_id)
    logger.info(
        "building_upgrade_queued",
        extra={
            "city_id": city.id,
            "building": building_name,
            "target_level": target_level,
            "finish_time": finish_time.isoformat(),
        },
    )
    return queue_entry


def calculate_upgrade_cost(building: models.Building) -> Dict[str, float]:
    """Calculate resource costs for the next upgrade level."""

    base = get_building_costs().get(building.name, {"wood": 100, "clay": 100, "iron": 100})
    multiplier = 1.2 ** max(building.level - 1, 0)
    return {resource: value * multiplier for resource, value in base.items()}


def process_building_queues(db: Session) -> List[dict]:
    """Finalize completed building queues and update related progress."""

    now = datetime.utcnow()
    finished_queues = (
        db.query(models.BuildingQueue)
        .filter(models.BuildingQueue.finish_time <= now)
        .options(selectinload(models.BuildingQueue.city))
        .all()
    )
    finished_info: List[dict] = []
    for queue_entry in finished_queues:
        city = queue_entry.city or db.query(models.City).filter(models.City.id == queue_entry.city_id).first()
        building = (
            db.query(models.Building)
            .filter(
                models.Building.city_id == queue_entry.city_id,
                models.Building.name == queue_entry.building_type,
            )
            .first()
        )
        if not building:
            building = models.Building(
                city_id=queue_entry.city_id,
                name=queue_entry.building_type,
                level=0,
            )
            db.add(building)
            db.flush()
        building.level = max(building.level, queue_entry.target_level)
        finished_info.append(
            {
                "city_id": queue_entry.city_id,
                "building_type": queue_entry.building_type,
                "target_level": queue_entry.target_level,
            }
        )
        if city and city.owner:
            quest_service.handle_event(
                db,
                city.owner,
                "building_finished",
                {"building_type": queue_entry.building_type, "level": building.level},
            )
            from .achievement import update_achievement_progress

            update_achievement_progress(
                db,
                city.owner_id,
                "build_level",
                absolute_value=building.level,
            )
        db.delete(queue_entry)
    if finished_queues:
        db.commit()
        logger.info(
            "building_queues_completed",
            extra={"count": len(finished_queues), "cities": [item["city_id"] for item in finished_info]},
        )
    return finished_info
