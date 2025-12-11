from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

from .. import models
from . import event as event_service
from . import production, ranking, quest as quest_service
from . import premium as premium_service
from . import production, ranking

UNIT_COSTS: Dict[str, Dict[str, float]] = {
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

TRAINING_TIMES: Dict[str, int] = {
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
        for resource, cost in UNIT_COSTS.get(unit_type, {"wood": 10, "clay": 10, "iron": 10}).items()
    }
    production.recalculate_resources(db, city)
    production.pay_cost(city, total_cost)

    base_time = TRAINING_TIMES.get(unit_type, 45)
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
    return queue_entry


def process_troop_queues(db: Session) -> List[dict]:
    now = datetime.utcnow()
    finished_queues = db.query(models.TroopQueue).filter(models.TroopQueue.finish_time <= now).all()
    finished_info: List[dict] = []
    if not finished_queues:
        return []
    owner_id = None
    for queue_entry in finished_queues:
        city = db.query(models.City).filter(models.City.id == queue_entry.city_id).first()
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
        db.delete(queue_entry)
    db.commit()
    return finished_info
        city = db.query(models.City).filter(models.City.id == queue_entry.city_id).first()
        if city and city.owner:
            owner_id = city.owner_id
            quest_service.handle_event(
                db,
                city.owner,
                "troops_trained",
                {"unit_type": queue_entry.troop_type, "amount": queue_entry.amount},
            )
        db.delete(queue_entry)
        if city:
            from .achievement import update_achievement_progress

            update_achievement_progress(
                db,
                city.owner_id,
                "train_troops",
                increment=queue_entry.amount,
            )
    db.commit()
    if finished_queues and city:
        db.refresh(troop)
        ranking.recalculate_player_and_alliance_scores(db, city.owner_id)
    db.refresh(troop)
    if owner_id:
        ranking.recalculate_player_and_alliance_scores(db, owner_id)
    return finished_queues
