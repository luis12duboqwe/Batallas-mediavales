"""Troop training and queue management services."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..utils import utc_now
from . import event as event_service
from . import premium as premium_service
from . import production, quest as quest_service, ranking, research as research_service

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_unit_costs() -> Dict[str, Dict[str, float]]:
    """Return cached unit training costs."""

    return {
        "basic_infantry": {"wood": 50, "clay": 30, "iron": 20},
        "heavy_infantry": {"wood": 70, "clay": 60, "iron": 50},
        "archer": {"wood": 80, "clay": 40, "iron": 40},
        "fast_cavalry": {"wood": 120, "clay": 80, "iron": 100},
        "heavy_cavalry": {"wood": 200, "clay": 150, "iron": 200},
        "spy": {"wood": 40, "clay": 40, "iron": 40},
        "ram": {"wood": 300, "clay": 200, "iron": 150},
        "catapult": {"wood": 350, "clay": 250, "iron": 300},
        "noble": {"wood": 1000, "clay": 1000, "iron": 1000},
    }


@lru_cache(maxsize=1)
def get_training_times() -> Dict[str, int]:
    """Return cached training durations per unit."""

    return {
        "basic_infantry": 45,
        "heavy_infantry": 60,
        "archer": 50,
        "fast_cavalry": 70,
        "heavy_cavalry": 80,
        "spy": 30,
        "ram": 90,
        "catapult": 120,
    }


UNIT_COSTS: Dict[str, Dict[str, float]] = {
    "basic_infantry": {"wood": 60, "clay": 40, "iron": 25},
    "heavy_infantry": {"wood": 90, "clay": 75, "iron": 60},
    "archer": {"wood": 85, "clay": 50, "iron": 55},
    "fast_cavalry": {"wood": 150, "clay": 110, "iron": 120},
    "heavy_cavalry": {"wood": 260, "clay": 200, "iron": 260},
    "spy": {"wood": 55, "clay": 55, "iron": 50},
    "ram": {"wood": 360, "clay": 260, "iron": 220},
    "catapult": {"wood": 380, "clay": 300, "iron": 350},
    "noble": {"wood": 1200, "clay": 1200, "iron": 1200},
}

TRAINING_TIMES: Dict[str, int] = {
    "basic_infantry": 60,
    "heavy_infantry": 75,
    "archer": 70,
    "fast_cavalry": 95,
    "heavy_cavalry": 130,
    "spy": 45,
    "ram": 140,
    "catapult": 180,
}


UNIT_REQUIREMENTS: Dict[str, Dict[str, int]] = {
    "basic_infantry": {"barracks": 1},
    "heavy_infantry": {"barracks": 3, "smithy": 1},
    "archer": {"barracks": 5, "smithy": 3},
    "fast_cavalry": {"stable": 1},
    "heavy_cavalry": {"stable": 5, "smithy": 5},
    "spy": {"stable": 1},
    "ram": {"workshop": 1},
    "catapult": {"workshop": 5},
    "noble": {"town_hall": 20, "workshop": 10},
}

# RESEARCH_COSTS is now handled in research service, but we might need it here if we want to keep the old logic
# For now, I will remove it as it is duplicated in research service.

def check_requirements(city: models.City, unit_type: str):
    # Check buildings
    reqs = UNIT_REQUIREMENTS.get(unit_type, {})
    for building_name, level in reqs.items():
        building = next((b for b in city.buildings if b.name == building_name), None)
        if not building or building.level < level:
            raise ValueError(f"Requirement not met: {building_name} level {level}")
            
    # Check research
    if not research_service.is_researched(db=Session.object_session(city), city_id=city.id, tech_name=unit_type):
        raise ValueError(f"Unit {unit_type} not researched")


def research_unit(db: Session, city: models.City, unit_type: str):
    # Delegate to research service
    research_service.research_tech(db, city, unit_type)


def queue_training(
    db: Session, city: models.City, unit_type: str, quantity: int
) -> models.TroopQueue:
    """Add a troop training order to the queue after validation and payment."""

    if quantity <= 0:
        raise ValueError("Quantity must be positive")

    status = premium_service.get_or_create_status(db, city.owner)
    existing_queue = (
        db.query(models.TroopQueue).filter(models.TroopQueue.city_id == city.id).count()
    )
    allowed_slots = premium_service.get_troop_queue_limit(status)
    if existing_queue >= allowed_slots:
        raise ValueError("No troop training queue slots available")

    check_requirements(city, unit_type)

    total_cost = {
        resource: cost * quantity
        for resource, cost in get_unit_costs()
        .get(unit_type, {"wood": 10, "clay": 10, "iron": 10})
        .items()
    }
    production.recalculate_resources(db, city)
    
    if not production.check_cost(city, total_cost):
        raise ValueError("Insufficient resources")
        
    production.pay_cost(city, total_cost)

    base_time = get_training_times().get(unit_type, 45)
    modifiers = event_service.get_active_modifiers(db)
    training_speed = modifiers.get("troop_training_speed", 1.0)
    duration_seconds = base_time * quantity * training_speed
    finish_time = utc_now() + timedelta(seconds=duration_seconds)

    queue_entry = models.TroopQueue(
        city_id=city.id,
        troop_type=unit_type,
        amount=quantity,
        finish_time=finish_time,
    )
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    logger.info(
        "troop_training_queued",
        extra={
            "city_id": city.id,
            "unit_type": unit_type,
            "quantity": quantity,
            "finish_time": finish_time.isoformat(),
        },
    )
    return queue_entry


def process_troop_queues(db: Session) -> List[dict]:
    """Process completed troop training queues and update progress."""

    now = utc_now()
    finished_queues = (
        db.query(models.TroopQueue)
        .filter(models.TroopQueue.finish_time <= now)
        .options(selectinload(models.TroopQueue.city))
        .all()
    )
    if not finished_queues:
        return []

    finished_info: List[dict] = []
    updated_owners: set[int] = set()
    for queue_entry in finished_queues:
        city = (
            queue_entry.city
            or db.query(models.City)
            .filter(models.City.id == queue_entry.city_id)
            .first()
        )
        troop = (
            db.query(models.Troop)
            .filter(
                models.Troop.city_id == queue_entry.city_id,
                models.Troop.unit_type == queue_entry.troop_type,
            )
            .first()
        )
        if not troop:
            troop = models.Troop(
                city_id=queue_entry.city_id,
                unit_type=queue_entry.troop_type,
                quantity=0,
            )
            db.add(troop)
            db.flush()
        troop.quantity += queue_entry.amount
        finished_info.append(
            {
                "city_id": queue_entry.city_id,
                "troop_type": queue_entry.troop_type,
                "amount": queue_entry.amount,
            }
        )
        if city and city.owner:
            updated_owners.add(city.owner_id)
            quest_service.handle_event(
                db,
                city.owner,
                "troops_trained",
                {"unit_type": queue_entry.troop_type, "amount": queue_entry.amount},
            )
            from .achievement import update_achievement_progress

            update_achievement_progress(
                db,
                city.owner_id,
                "train_troops",
                increment=queue_entry.amount,
            )
        db.delete(queue_entry)
    db.commit()
    for owner_id in updated_owners:
        if owner_id and finished_info:
            city_id = finished_info[0]["city_id"]
            world_id = (
                db.query(models.City)
                .filter(models.City.id == city_id)
                .first()
            )
            if world_id:
                ranking.recalculate_player_and_alliance_scores(db, owner_id, world_id.world_id)
    logger.info(
        "troop_training_completed",
        extra={
            "count": len(finished_info),
            "cities": [item["city_id"] for item in finished_info],
        },
    )
    return finished_info


def cancel_troop_queue(db: Session, queue_id: int, user_id: int) -> bool:
    """Cancel a troop training queue and refund a percentage of resources."""
    queue_entry = (
        db.query(models.TroopQueue)
        .join(models.City)
        .filter(models.TroopQueue.id == queue_id, models.City.owner_id == user_id)
        .first()
    )
    if not queue_entry:
        return False

    city = queue_entry.city
    
    # Calculate refund (e.g., 80% of cost)
    unit_cost = get_unit_costs().get(queue_entry.troop_type, {"wood": 0, "clay": 0, "iron": 0})
    total_cost = {r: c * queue_entry.amount for r, c in unit_cost.items()}
    
    refund_factor = 0.8
    refund = {r: int(amount * refund_factor) for r, amount in total_cost.items()}
    
    production.recalculate_resources(db, city)
    for resource, amount in refund.items():
        current_val = getattr(city, resource)
        setattr(city, resource, current_val + amount)
        
    db.delete(queue_entry)
    db.commit()
    return True
