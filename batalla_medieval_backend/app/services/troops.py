"""Troop training and queue management services."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List

from sqlalchemy.orm import Session, selectinload

from .. import models
from . import event as event_service
from . import premium as premium_service
from . import production, quest as quest_service, ranking

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


def queue_training(db: Session, city: models.City, unit_type: str, quantity: int) -> models.TroopQueue:
    """Add a troop training order to the queue after validation and payment."""

    if quantity <= 0:
        raise ValueError("Quantity must be positive")

    status = premium_service.get_or_create_status(db, city.owner)
    existing_queue = (
        db.query(models.TroopQueue)
        .filter(models.TroopQueue.city_id == city.id)
        .count()
    )
    allowed_slots = premium_service.get_troop_queue_limit(status)
    if existing_queue >= allowed_slots:
        raise ValueError("No troop training queue slots available")

    total_cost = {
        resource: cost * quantity
        for resource, cost in get_unit_costs().get(unit_type, {"wood": 10, "clay": 10, "iron": 10}).items()
    }
    production.recalculate_resources(db, city)
    production.pay_cost(city, total_cost)

    base_time = get_training_times().get(unit_type, 45)
    modifiers = event_service.get_active_modifiers(db)
    training_speed = modifiers.get("troop_training_speed", 1.0)
    duration_seconds = base_time * quantity * training_speed
    finish_time = datetime.utcnow() + timedelta(seconds=duration_seconds)

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

    now = datetime.utcnow()
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
        city = queue_entry.city or db.query(models.City).filter(models.City.id == queue_entry.city_id).first()
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
                city_id=queue_entry.city_id, unit_type=queue_entry.troop_type, quantity=0
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
        ranking.recalculate_player_and_alliance_scores(db, owner_id)
    logger.info(
        "troop_training_completed",
        extra={"count": len(finished_info), "cities": [item["city_id"] for item in finished_info]},
    )
    return finished_info
