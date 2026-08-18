"""Canonical unit, research and training definitions.

The API, research service, training service and frontend availability endpoint all
consume this module so displayed prices and requirements cannot drift from what
the server charges.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from sqlalchemy.orm import Session

from .. import models


UNIT_ORDER = [
    "basic_infantry",
    "heavy_infantry",
    "archer",
    "fast_cavalry",
    "heavy_cavalry",
    "spy",
    "ram",
    "catapult",
    "noble",
]

UNIT_CATALOG: Dict[str, Dict[str, Any]] = {
    "basic_infantry": {
        "training_cost": {"wood": 50.0, "clay": 30.0, "iron": 20.0},
        "training_time_seconds": 45,
        "training_requirements": {"barracks": 1},
        "research_cost": {},
        "research_requirements": {},
        "researchable": False,
    },
    "heavy_infantry": {
        "training_cost": {"wood": 70.0, "clay": 60.0, "iron": 50.0},
        "training_time_seconds": 60,
        "training_requirements": {"barracks": 3, "smithy": 1},
        "research_cost": {"wood": 500.0, "clay": 400.0, "iron": 300.0},
        "research_requirements": {"barracks": 3},
        "researchable": True,
    },
    "archer": {
        "training_cost": {"wood": 80.0, "clay": 40.0, "iron": 40.0},
        "training_time_seconds": 50,
        "training_requirements": {"barracks": 5, "smithy": 3},
        "research_cost": {"wood": 600.0, "clay": 300.0, "iron": 300.0},
        "research_requirements": {"barracks": 5},
        "researchable": True,
    },
    "fast_cavalry": {
        "training_cost": {"wood": 120.0, "clay": 80.0, "iron": 100.0},
        "training_time_seconds": 70,
        "training_requirements": {"stable": 1},
        "research_cost": {"wood": 1000.0, "clay": 800.0, "iron": 600.0},
        "research_requirements": {"stable": 3},
        "researchable": True,
    },
    "heavy_cavalry": {
        "training_cost": {"wood": 200.0, "clay": 150.0, "iron": 200.0},
        "training_time_seconds": 80,
        "training_requirements": {"stable": 5, "smithy": 5},
        "research_cost": {"wood": 2000.0, "clay": 1500.0, "iron": 1500.0},
        "research_requirements": {"stable": 10},
        "researchable": True,
    },
    "spy": {
        "training_cost": {"wood": 40.0, "clay": 40.0, "iron": 40.0},
        "training_time_seconds": 30,
        "training_requirements": {"stable": 1},
        "research_cost": {"wood": 200.0, "clay": 200.0, "iron": 200.0},
        "research_requirements": {"stable": 1},
        "researchable": True,
    },
    "ram": {
        "training_cost": {"wood": 300.0, "clay": 200.0, "iron": 150.0},
        "training_time_seconds": 90,
        "training_requirements": {"workshop": 1},
        "research_cost": {"wood": 1500.0, "clay": 1000.0, "iron": 1000.0},
        "research_requirements": {"barracks": 10},
        "researchable": True,
    },
    "catapult": {
        "training_cost": {"wood": 350.0, "clay": 250.0, "iron": 300.0},
        "training_time_seconds": 120,
        "training_requirements": {"workshop": 5},
        "research_cost": {"wood": 2000.0, "clay": 1500.0, "iron": 1500.0},
        "research_requirements": {"barracks": 15},
        "researchable": True,
    },
    "noble": {
        "training_cost": {"wood": 1000.0, "clay": 1000.0, "iron": 1000.0},
        "training_time_seconds": 45,
        "training_requirements": {"town_hall": 20, "workshop": 10},
        "research_cost": {"wood": 10000.0, "clay": 10000.0, "iron": 10000.0},
        "research_requirements": {"town_hall": 20},
        "researchable": True,
    },
}


def get_unit(unit_type: str) -> Dict[str, Any]:
    definition = UNIT_CATALOG.get(unit_type)
    if definition is None:
        raise ValueError(f"Unknown unit type: {unit_type}")
    return deepcopy(definition)


def _building_levels(city: models.City) -> Dict[str, int]:
    return {building.name: int(building.level) for building in city.buildings}


def requirements_met(city: models.City, requirements: Dict[str, int]) -> bool:
    levels = _building_levels(city)
    return all(levels.get(name, 0) >= level for name, level in requirements.items())


def first_missing_requirement(city: models.City, requirements: Dict[str, int]) -> tuple[str, int] | None:
    levels = _building_levels(city)
    for name, level in requirements.items():
        if levels.get(name, 0) < level:
            return name, level
    return None


def is_researched(db: Session, city_id: int, unit_type: str) -> bool:
    if unit_type == "basic_infantry":
        return True
    return (
        db.query(models.Research.id)
        .filter(
            models.Research.city_id == city_id,
            models.Research.tech_name == unit_type,
        )
        .first()
        is not None
    )


def _can_afford(city: models.City, cost: Dict[str, float]) -> bool:
    return all(float(getattr(city, resource)) >= amount for resource, amount in cost.items())


def get_availability(db: Session, city: models.City) -> list[dict]:
    """Return the complete server-authoritative unit catalog for one city."""

    result = []
    for unit_type in UNIT_ORDER:
        definition = get_unit(unit_type)
        researched = is_researched(db, city.id, unit_type)
        train_requirements_met = requirements_met(
            city, definition["training_requirements"]
        )
        research_requirements_met = requirements_met(
            city, definition["research_requirements"]
        )
        researchable = bool(definition["researchable"])

        result.append(
            {
                "unit_type": unit_type,
                "training_cost": definition["training_cost"],
                "training_time_seconds": definition["training_time_seconds"],
                "training_requirements": definition["training_requirements"],
                "research_cost": definition["research_cost"],
                "research_requirements": definition["research_requirements"],
                "researched": researched,
                "training_requirements_met": train_requirements_met,
                "research_requirements_met": research_requirements_met,
                "can_train": (
                    researched
                    and train_requirements_met
                    and _can_afford(city, definition["training_cost"])
                ),
                "can_research": (
                    researchable
                    and not researched
                    and research_requirements_met
                    and _can_afford(city, definition["research_cost"])
                ),
            }
        )
    return result
