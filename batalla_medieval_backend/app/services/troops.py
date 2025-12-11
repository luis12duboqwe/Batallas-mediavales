from typing import Dict

from sqlalchemy.orm import Session

from .. import models
from . import production

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


def queue_training(db: Session, city: models.City, unit_type: str, quantity: int) -> models.Troop:
    troop = db.query(models.Troop).filter(models.Troop.city_id == city.id, models.Troop.unit_type == unit_type).first()
    if not troop:
        troop = models.Troop(city_id=city.id, unit_type=unit_type, quantity=0)
        db.add(troop)
        db.commit()
        db.refresh(troop)
    total_cost = {resource: cost * quantity for resource, cost in UNIT_COSTS.get(unit_type, {"wood": 10, "clay": 10, "iron": 10}).items()}
    production.recalculate_resources(db, city)
    production.pay_cost(city, total_cost)
    troop.quantity += quantity
    db.add(troop)
    db.commit()
    db.refresh(troop)
    return troop
