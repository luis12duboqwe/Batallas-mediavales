from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

from .. import models
from . import production, ranking

BUILDING_COSTS: Dict[str, Dict[str, float]] = {
    "town_hall": {"wood": 200, "clay": 150, "iron": 100},
    "barracks": {"wood": 150, "clay": 150, "iron": 120},
    "stable": {"wood": 250, "clay": 200, "iron": 200},
}

BASE_BUILD_TIME_SECONDS = 300


def queue_upgrade(db: Session, city: models.City, building_name: str) -> models.BuildingQueue:
    existing_queue = db.query(models.BuildingQueue).filter(models.BuildingQueue.city_id == city.id).first()
    if existing_queue:
        raise ValueError("A building upgrade is already in progress for this city")

    building = (
        db.query(models.Building).filter(models.Building.city_id == city.id, models.Building.name == building_name).first()
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
    db.refresh(building)
    ranking.recalculate_player_and_alliance_scores(db, city.owner_id)
    return building
    db.refresh(queue_entry)
    return queue_entry


def calculate_upgrade_cost(building: models.Building) -> Dict[str, float]:
    base = BUILDING_COSTS.get(building.name, {"wood": 100, "clay": 100, "iron": 100})
    multiplier = 1.2 ** (building.level - 1)
    return {resource: value * multiplier for resource, value in base.items()}


def process_building_queues(db: Session) -> List[models.BuildingQueue]:
    now = datetime.utcnow()
    finished_queues = (
        db.query(models.BuildingQueue)
        .filter(models.BuildingQueue.finish_time <= now)
        .all()
    )
    for queue_entry in finished_queues:
        building = (
            db.query(models.Building)
            .filter(models.Building.city_id == queue_entry.city_id, models.Building.name == queue_entry.building_type)
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
        db.delete(queue_entry)
    db.commit()
    return finished_queues
