"""Building service utilities for handling upgrades and queues."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..utils import utc_now
from . import premium as premium_service
from . import production, quest as quest_service, ranking, notification as notification_service

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


@lru_cache(maxsize=1)
def get_building_costs() -> Dict[str, Dict[str, float]]:
    """Return cached building cost definitions."""
    return BUILDING_COSTS


def get_available_buildings(db: Session, city: models.City) -> List[dict]:
    """Return list of all buildings with their status for the city."""
    
    existing_map = {b.name: b for b in city.buildings}
    result = []
    
    all_buildings = BUILDING_COSTS.keys()
    
    for name in all_buildings:
        building = existing_map.get(name)
        current_level = building.level if building else 0
        
        # Calculate cost for next level
        # We simulate a building object for the cost calculator
        temp_building = models.Building(name=name, level=current_level + 1)
        cost = calculate_upgrade_cost(temp_building)
        
        # Check prerequisites
        prereqs = BUILDING_PREREQUISITES.get(name, {})
        requirements_met = True
        for req_name, req_level in prereqs.items():
            existing_req = existing_map.get(req_name)
            if not existing_req or existing_req.level < req_level:
                requirements_met = False
                break
        
        build_time = BASE_BUILD_TIME_SECONDS * (current_level + 1)
        
        result.append({
            "name": name,
            "level": current_level,
            "cost": cost,
            "requirements_met": requirements_met,
            "requirements": prereqs,
            "build_time": build_time
        })
        
    return result


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

    # Check prerequisites
    prereqs = BUILDING_PREREQUISITES.get(building_name, {})
    if prereqs:
        existing_buildings = {b.name: b.level for b in city.buildings}
        for req_name, req_level in prereqs.items():
            if existing_buildings.get(req_name, 0) < req_level:
                raise ValueError(f"Prerequisite not met: {req_name} level {req_level} required")

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
    
    if not production.check_cost(city, cost):
        raise ValueError("Insufficient resources")
        
    production.pay_cost(city, cost)

    target_level = building.level + 1
    duration_seconds = BASE_BUILD_TIME_SECONDS * target_level
    finish_time = utc_now() + timedelta(seconds=duration_seconds)

    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type=building_name,
        target_level=target_level,
        finish_time=finish_time,
    )
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    ranking.recalculate_player_and_alliance_scores(db, city.owner_id, city.world_id)
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

    now = utc_now()
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
        
        # Check for World Wonder Win Condition
        if building.name == "world_wonder" and building.level >= 100:
            world = db.query(models.World).filter(models.World.id == city.world_id).first()
            if world and world.is_active:
                world.is_active = False
                world.ended_at = utc_now()
                world.winner_id = city.owner_id
                # If user is in an alliance, set winner_alliance_id
                # Assuming city.owner.alliance_id exists or similar
                # For now, just winner_id
                
                notification_service.create_notification(
                    db,
                    city.owner,
                    title="¡Victoria!",
                    body="¡Has completado la Maravilla del Mundo y ganado el servidor!",
                    notification_type="world_won",
                )

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


def cancel_building_queue(db: Session, queue_id: int, user_id: int) -> bool:
    """Cancel a building queue and refund a percentage of resources."""
    queue_entry = (
        db.query(models.BuildingQueue)
        .join(models.City)
        .filter(models.BuildingQueue.id == queue_id, models.City.owner_id == user_id)
        .first()
    )
    if not queue_entry:
        return False

    city = queue_entry.city
    
    # Calculate refund (e.g., 80% of cost)
    # Re-calculate cost for the target level
    dummy_building = models.Building(name=queue_entry.building_type, level=queue_entry.target_level - 1)
    cost = calculate_upgrade_cost(dummy_building)
    
    refund_factor = 0.8
    refund = {r: int(amount * refund_factor) for r, amount in cost.items()}
    
    production.recalculate_resources(db, city)
    for resource, amount in refund.items():
        current_val = getattr(city, resource)
        setattr(city, resource, current_val + amount)
        
    db.delete(queue_entry)
    db.commit()
    return True
