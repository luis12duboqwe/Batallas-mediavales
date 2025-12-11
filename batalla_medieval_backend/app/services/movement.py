from datetime import datetime, timedelta
import math

from sqlalchemy.orm import Session

from .. import models
from . import espionage

UNIT_SPEED = {
    "basic_infantry": 0.6,
    "heavy_infantry": 0.55,
    "archer": 0.7,
    "fast_cavalry": 1.2,
    "heavy_cavalry": 0.9,
    "spy": 1.5,
    "ram": 0.5,
    "catapult": 0.45,
}


def calculate_distance(origin: models.City, target: models.City) -> float:
    return math.hypot(origin.x - target.x, origin.y - target.y)


def send_movement(
    db: Session,
    origin_city: models.City,
    target_city_id: int,
    movement_type: str,
    spy_count: int = 0,
) -> models.Movement:
    target_city = db.query(models.City).filter(models.City.id == target_city_id).first()
    if not target_city:
        raise ValueError("Target city not found")
    if movement_type != "spy":
        spy_count = 0
    if movement_type == "spy":
        spy_troop = (
            db.query(models.Troop)
            .filter(models.Troop.city_id == origin_city.id, models.Troop.unit_type == "spy")
            .first()
        )
        if not spy_troop or spy_troop.quantity < spy_count:
            raise ValueError("Not enough spies to send this mission")
        spy_troop.quantity -= spy_count
        db.add(spy_troop)
        db.commit()
        db.refresh(spy_troop)
    speed = UNIT_SPEED.get("fast_cavalry" if movement_type == "spy" else "basic_infantry", 0.6)
    distance = calculate_distance(origin_city, target_city)
    hours = distance / speed
    arrival_time = datetime.utcnow() + timedelta(hours=hours)
    movement = models.Movement(
        origin_city_id=origin_city.id,
        target_city_id=target_city.id,
        movement_type=movement_type,
        spy_count=spy_count,
        arrival_time=arrival_time,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def resolve_due_movements(db: Session):
    now = datetime.utcnow()
    movements = (
        db.query(models.Movement)
        .filter(models.Movement.arrival_time <= now, models.Movement.status == "ongoing")
        .all()
    )
    resolved = []
    for movement in movements:
        if movement.movement_type == "spy":
            espionage.resolve_spy(db, movement)
        movement.status = "completed"
        db.add(movement)
        resolved.append(movement)
    db.commit()
    return resolved
