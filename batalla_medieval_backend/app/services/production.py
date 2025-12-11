from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Session

from .. import models

PRODUCTION_RATES = {
    "wood": 30.0,
    "clay": 25.0,
    "iron": 20.0,
}

LOYALTY_RECOVERY_PER_HOUR = 2.0


def recalculate_resources(db: Session, city: models.City, return_gains: bool = False) -> models.City | tuple[models.City, Dict[str, float]]:
    now = datetime.utcnow()
    elapsed_minutes = (now - city.last_production).total_seconds() / 60
    gains: Dict[str, float] = {}
    for resource, rate in PRODUCTION_RATES.items():
        current_value = getattr(city, resource)
        gained = rate * elapsed_minutes
        gains[resource] = gained
        setattr(city, resource, current_value + gained)
    modifier = city.world.resource_modifier if city.world else 1.0
    for resource, rate in PRODUCTION_RATES.items():
        current_value = getattr(city, resource)
        setattr(city, resource, current_value + rate * elapsed_minutes * modifier)
    loyalty_gain = LOYALTY_RECOVERY_PER_HOUR * (elapsed_minutes / 60)
    city.loyalty = min(100.0, city.loyalty + loyalty_gain)
    city.last_production = now
    db.add(city)
    db.commit()
    db.refresh(city)
    if return_gains:
        return city, gains
    return city


def pay_cost(city: models.City, cost: Dict[str, float]):
    for resource, amount in cost.items():
        setattr(city, resource, getattr(city, resource) - amount)
