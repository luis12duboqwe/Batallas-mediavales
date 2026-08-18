from sqlalchemy.orm import Session

from .. import models
from . import production, unit_catalog


def get_researched_techs(db: Session, city_id: int):
    return db.query(models.Research).filter(models.Research.city_id == city_id).all()


def is_researched(db: Session, city_id: int, tech_name: str) -> bool:
    return unit_catalog.is_researched(db, city_id, tech_name)


def _sync_city_researched_units(db: Session, city: models.City) -> None:
    """Keep the legacy City JSON mirror aligned without deleting old progress."""

    researched = ["basic_infantry"]
    researched.extend(
        unit
        for unit in list(city.researched_units or [])
        if unit != "basic_infantry"
    )
    researched.extend(
        row.tech_name
        for row in (
            db.query(models.Research)
            .filter(models.Research.city_id == city.id)
            .order_by(models.Research.id.asc())
            .all()
        )
        if row.tech_name != "basic_infantry"
    )
    city.researched_units = list(dict.fromkeys(researched))
    db.add(city)


def research_tech(db: Session, city: models.City, tech_name: str) -> models.Research:
    """Research a unit using the same server catalog exposed to the client."""

    definition = unit_catalog.get_unit(tech_name)
    if not definition["researchable"]:
        raise ValueError("Technology is already available by default")

    city, production_gains = production.lock_and_recalculate_resources(db, city)
    db.expire(city, ["buildings"])

    if is_researched(db, city.id, tech_name):
        db.rollback()
        raise ValueError("Technology already researched")

    missing = unit_catalog.first_missing_requirement(
        city, definition["research_requirements"]
    )
    if missing:
        req_name, req_level = missing
        db.rollback()
        raise ValueError(
            f"Prerequisite not met: {req_name} level {req_level} required"
        )

    cost = definition["research_cost"]
    if not production.check_cost(city, cost):
        db.rollback()
        raise ValueError("Insufficient resources")

    production.pay_cost(city, cost)

    research = models.Research(city_id=city.id, tech_name=tech_name, level=1)
    db.add(research)
    db.flush()
    _sync_city_researched_units(db, city)
    db.commit()
    db.refresh(research)
    production.record_resource_gains(db, city, production_gains)
    return research
