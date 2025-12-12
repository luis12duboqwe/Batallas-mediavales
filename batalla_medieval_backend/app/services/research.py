from typing import Dict
from sqlalchemy.orm import Session
from .. import models
from . import production

RESEARCH_COSTS: Dict[str, Dict[str, float]] = {
    "heavy_infantry": {"wood": 500, "clay": 400, "iron": 300},
    "archer": {"wood": 600, "clay": 300, "iron": 300},
    "fast_cavalry": {"wood": 1000, "clay": 800, "iron": 600},
    "heavy_cavalry": {"wood": 2000, "clay": 1500, "iron": 1500},
    "spy": {"wood": 200, "clay": 200, "iron": 200},
    "ram": {"wood": 1500, "clay": 1000, "iron": 1000},
    "catapult": {"wood": 2000, "clay": 1500, "iron": 1500},
    "noble": {"wood": 10000, "clay": 10000, "iron": 10000},
}

RESEARCH_PREREQUISITES: Dict[str, Dict[str, int]] = {
    "heavy_infantry": {"barracks": 3},
    "archer": {"barracks": 5},
    "fast_cavalry": {"stable": 3},
    "heavy_cavalry": {"stable": 10},
    "spy": {"stable": 1},
    "ram": {"barracks": 10},
    "catapult": {"barracks": 15},
    "noble": {"town_hall": 20},
}

def get_researched_techs(db: Session, city_id: int):
    return db.query(models.Research).filter(models.Research.city_id == city_id).all()

def is_researched(db: Session, city_id: int, tech_name: str) -> bool:
    if tech_name == "basic_infantry":
        return True
    return db.query(models.Research).filter(models.Research.city_id == city_id, models.Research.tech_name == tech_name).first() is not None

def research_tech(db: Session, city: models.City, tech_name: str):
    if is_researched(db, city.id, tech_name):
        raise ValueError("Technology already researched")

    cost = RESEARCH_COSTS.get(tech_name)
    if not cost:
        raise ValueError("Invalid technology")

    # Check prerequisites
    prereqs = RESEARCH_PREREQUISITES.get(tech_name, {})
    existing_buildings = {b.name: b.level for b in city.buildings}
    for req_name, req_level in prereqs.items():
        if existing_buildings.get(req_name, 0) < req_level:
            raise ValueError(f"Prerequisite not met: {req_name} level {req_level} required")

    production.recalculate_resources(db, city)
    if not production.check_cost(city, cost):
        raise ValueError("Insufficient resources")

    production.pay_cost(city, cost)
    
    research = models.Research(city_id=city.id, tech_name=tech_name, level=1)
    db.add(research)
    db.commit()
    return research
