"""Server-side unit availability helpers backed by the versioned balance catalog."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from sqlalchemy.orm import Session

from .. import models
from . import balance, upkeep as upkeep_service

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


def _unit_population(unit_type: str, quantity: int) -> int:
    definition = UNIT_CATALOG.get(unit_type)
    if definition is None:
        return 0
    return max(int(quantity), 0) * int(definition.get("population", 1))


def get_population_capacity(city: models.City) -> int:
    """Return persisted base capacity plus the live farm bonus.

    ``population_max`` remains the settlement's persisted base. This preserves
    custom/test/world values and prevents a farm completion from overwriting
    them with a hard-coded city default. Camps cannot build farms, so their base
    capacity is returned unchanged.
    """

    base_capacity = max(int(city.population_max), 0)
    if getattr(city, "settlement_type", "city") == "camp":
        return base_capacity
    farm_level = _building_levels(city).get("farm", 0)
    return base_capacity + farm_level * balance.POPULATION_PER_FARM_LEVEL


def get_population_used(db: Session, city: models.City) -> int:
    """Return committed population, including troops temporarily away."""

    used = sum(
        _unit_population(troop.unit_type, troop.quantity)
        for troop in city.troops
    )

    outgoing = (
        db.query(models.Movement)
        .filter(
            models.Movement.origin_city_id == city.id,
            models.Movement.status == "ongoing",
            models.Movement.movement_type.in_(["attack", "spy", "reinforce"]),
        )
        .all()
    )
    for movement in outgoing:
        if movement.movement_type == "spy":
            used += _unit_population("spy", int(movement.spy_count or 0))
        else:
            for unit_type, quantity in (movement.troops or {}).items():
                used += _unit_population(unit_type, int(quantity))

    returning = (
        db.query(models.Movement)
        .filter(
            models.Movement.target_city_id == city.id,
            models.Movement.status == "ongoing",
            models.Movement.movement_type == "return",
        )
        .all()
    )
    for movement in returning:
        for unit_type, quantity in (movement.troops or {}).items():
            used += _unit_population(unit_type, int(quantity))

    return used


def get_population_reserved_for_training(db: Session, city_id: int) -> int:
    queues = (
        db.query(models.TroopQueue)
        .filter(models.TroopQueue.city_id == city_id)
        .all()
    )
    return sum(
        _unit_population(queue.troop_type, queue.amount)
        for queue in queues
    )


def get_population_available(db: Session, city: models.City) -> int:
    committed = get_population_used(db, city)
    reserved = get_population_reserved_for_training(db, city.id)
    return max(get_population_capacity(city) - committed - reserved, 0)


def has_population_capacity(
    db: Session,
    city: models.City,
    unit_type: str,
    quantity: int,
) -> bool:
    return _unit_population(unit_type, quantity) <= get_population_available(db, city)


def has_upkeep_capacity(
    db: Session,
    city: models.City,
    unit_type: str,
    quantity: int,
) -> bool:
    return upkeep_service.can_reserve_upkeep(db, city, unit_type, quantity)


def _can_afford(city: models.City, cost: Dict[str, float]) -> bool:
    return all(float(getattr(city, resource)) >= amount for resource, amount in cost.items())


def get_availability(db: Session, city: models.City) -> list[dict]:
    """Return the complete server-authoritative unit/research catalog for a city."""

    result = []
    population_available = get_population_available(db, city)
    population_capacity = get_population_capacity(city)
    upkeep_status = upkeep_service.get_upkeep_status(db, city)
    active_research = (
        db.query(models.ResearchQueue)
        .filter(models.ResearchQueue.city_id == city.id)
        .one_or_none()
    )
    research_queue_available = active_research is None

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
        population_cost = int(definition.get("population", 1))
        population_capacity_met = population_cost <= population_available
        unit_upkeep = float(definition.get("upkeep_per_hour", 0.0))
        upkeep_capacity_met = unit_upkeep <= float(
            upkeep_status["available_per_hour"]
        ) + 1e-9
        research_queued = bool(
            active_research is not None and active_research.tech_name == unit_type
        )
        combat = balance.UNIT_COMBAT_STATS[unit_type]

        result.append(
            {
                "unit_type": unit_type,
                "training_cost": definition["training_cost"],
                "training_time_seconds": definition["training_time_seconds"],
                "training_requirements": definition["training_requirements"],
                "research_cost": definition["research_cost"],
                "research_time_seconds": int(definition.get("research_time_seconds", 0)),
                "research_requirements": definition["research_requirements"],
                "researched": researched,
                "research_queued": research_queued,
                "training_requirements_met": train_requirements_met,
                "research_requirements_met": research_requirements_met,
                "population_cost": population_cost,
                "population_capacity": population_capacity,
                "population_available": population_available,
                "population_capacity_met": population_capacity_met,
                "upkeep_per_hour": unit_upkeep,
                "upkeep_used_per_hour": float(upkeep_status["used_per_hour"]),
                "upkeep_reserved_per_hour": float(upkeep_status["reserved_per_hour"]),
                "upkeep_capacity_per_hour": float(upkeep_status["capacity_per_hour"]),
                "upkeep_available_per_hour": float(upkeep_status["available_per_hour"]),
                "upkeep_capacity_met": upkeep_capacity_met,
                "movement_speed": float(balance.UNIT_SPEED[unit_type]),
                "carry_capacity": int(combat.get("carry", 0)),
                "attack": int(combat.get("attack", 0)),
                "defense_infantry": int(combat.get("def_inf", 0)),
                "defense_cavalry": int(combat.get("def_cav", 0)),
                "defense_siege": int(combat.get("def_siege", 0)),
                "combat_type": str(combat.get("type", "infantry")),
                "can_train": (
                    researched
                    and train_requirements_met
                    and population_capacity_met
                    and upkeep_capacity_met
                    and _can_afford(city, definition["training_cost"])
                ),
                "can_research": (
                    researchable
                    and not researched
                    and research_queue_available
                    and research_requirements_met
                    and _can_afford(city, definition["research_cost"])
                ),
            }
        )
    return result
