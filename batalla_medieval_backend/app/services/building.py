from typing import Dict

from sqlalchemy.orm import Session

from .. import models
from . import production, ranking

BUILDING_COSTS: Dict[str, Dict[str, float]] = {
    "town_hall": {"wood": 200, "clay": 150, "iron": 100},
    "barracks": {"wood": 150, "clay": 150, "iron": 120},
    "stable": {"wood": 250, "clay": 200, "iron": 200},
}


def queue_upgrade(db: Session, city: models.City, building_name: str) -> models.Building:
    building = (
        db.query(models.Building).filter(models.Building.city_id == city.id, models.Building.name == building_name).first()
    )
    if not building:
        building = models.Building(city_id=city.id, name=building_name, level=1)
        db.add(building)
        db.commit()
        db.refresh(building)
    cost = calculate_upgrade_cost(building)
    production.recalculate_resources(db, city)
    production.pay_cost(city, cost)
    building.level += 1
    db.add(building)
    db.commit()
    db.refresh(building)
    ranking.recalculate_player_and_alliance_scores(db, city.owner_id)
    return building


def calculate_upgrade_cost(building: models.Building) -> Dict[str, float]:
    base = BUILDING_COSTS.get(building.name, {"wood": 100, "clay": 100, "iron": 100})
    multiplier = 1.2 ** (building.level - 1)
    return {resource: value * multiplier for resource, value in base.items()}
