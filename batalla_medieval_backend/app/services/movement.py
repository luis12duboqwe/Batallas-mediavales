from datetime import datetime, timedelta
import math

from sqlalchemy.orm import Session

from .. import models

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
    target_city: models.City | None = None,
) -> models.Movement:
    target_city = target_city or db.query(models.City).filter(models.City.id == target_city_id).first()
    if not target_city:
        raise ValueError("Target city not found")
    speed = UNIT_SPEED.get("fast_cavalry" if movement_type == "spy" else "basic_infantry", 0.6)
    distance = calculate_distance(origin_city, target_city)
    hours = distance / speed
    arrival_time = datetime.utcnow() + timedelta(hours=hours)
    movement = models.Movement(
        origin_city_id=origin_city.id,
        target_city_id=target_city.id,
        movement_type=movement_type,
        arrival_time=arrival_time,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement
