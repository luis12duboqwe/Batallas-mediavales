from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Session

from .. import models
from . import event as event_service

PRODUCTION_RATES = {
    "wood": 30.0,
    "clay": 25.0,
    "iron": 20.0,
}

LOYALTY_RECOVERY_PER_HOUR = 2.0


def recalculate_resources(db: Session, city: models.City) -> models.City:
    now = datetime.utcnow()
    elapsed_minutes = (now - city.last_production).total_seconds() / 60
    modifiers = event_service.get_active_modifiers(db)
    for resource, rate in PRODUCTION_RATES.items():
        current_value = getattr(city, resource)
        adjusted_rate = rate * modifiers.get("production_speed", 1.0)
        setattr(city, resource, current_value + adjusted_rate * elapsed_minutes)
    loyalty_gain = LOYALTY_RECOVERY_PER_HOUR * (elapsed_minutes / 60)
    city.loyalty = min(100.0, city.loyalty + loyalty_gain)
    city.last_production = now
    db.add(city)
    db.commit()
    db.refresh(city)
    return city


def pay_cost(city: models.City, cost: Dict[str, float]):
    for resource, amount in cost.items():
        setattr(city, resource, getattr(city, resource) - amount)
