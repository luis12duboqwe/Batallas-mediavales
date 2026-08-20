"""Server-side unit availability helpers backed by the versioned balance catalog."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from sqlalchemy.orm import Session

from .. import models
from . import balance

# Compatibility aliases: definitions live only in ``balance``.
UNIT_ORDER = balance.UNIT_ORDER
UNIT_CATALOG = balance.UNIT_CATALOG


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


def first_missing_requirement(
    city: models.City, requirements: Dict[str, int]
) -> tuple[str, int] | None:
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
