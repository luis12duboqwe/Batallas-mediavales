"""Compatibility helpers over the canonical versioned balance catalog.

Historically this module carried a second set of Spanish-named prices and
formulas that disagreed with the live building/training services. BM-0040 keeps
these helper entry points for callers, but all values now come from
``app.services.balance``.
"""

from __future__ import annotations

from typing import Dict, Mapping

from . import balance

BALANCE_VERSION = balance.BALANCE_VERSION
BASE_BUILDING_COSTS = balance.BUILDING_COSTS
BASE_TROOP_COSTS: Dict[str, Dict[str, float]] = {
    unit_type: definition["training_cost"]
    for unit_type, definition in balance.UNIT_CATALOG.items()
}
BASE_TRAINING_TIMES: Dict[str, float] = {
    unit_type: float(definition["training_time_seconds"])
    for unit_type, definition in balance.UNIT_CATALOG.items()
}
STORAGE_BASE_CAPACITY = balance.STORAGE_BASE_CAPACITY
STORAGE_PER_WAREHOUSE_LEVEL = balance.STORAGE_PER_WAREHOUSE_LEVEL


def get_building_cost(building_type: str, level: int) -> Dict[str, float]:
    """Return the same upgrade quote used by the live building queue."""

    return balance.get_building_cost(building_type, level)


def get_troop_cost(troop_type: str, amount: int = 1) -> Dict[str, float]:
    """Return the same training cost used by the live troop queue."""

    if amount < 1:
        raise ValueError("Amount of troops must be >= 1")
    definition = balance.UNIT_CATALOG.get(troop_type)
    if definition is None:
        raise KeyError(f"Unknown troop type: {troop_type}")
    return {
        resource: float(value) * amount
        for resource, value in definition["training_cost"].items()
    }


def get_training_time(troop_type: str, building_level: int = 1) -> float:
    """Return canonical per-unit training seconds.

    The accepted live queue does not scale training time by building level.
    ``building_level`` remains only for backwards call compatibility.
    """

    if building_level < 1:
        raise ValueError("Building level must be >= 1")
    definition = balance.UNIT_CATALOG.get(troop_type)
    if definition is None:
        raise KeyError(f"Unknown troop type: {troop_type}")
    return float(definition["training_time_seconds"])


def get_storage_capacity(warehouse_level: int) -> float:
    return balance.get_storage_capacity(warehouse_level)


def enforce_storage_limits(
    resources: Mapping[str, float], storage_level: int
) -> Dict[str, float]:
    capacity = get_storage_capacity(storage_level)
    return {resource: min(amount, capacity) for resource, amount in resources.items()}


def calculate_population_used(troop_quantities: Mapping[str, int]) -> float:
    """Match the current live population model: one slot per troop."""

    return float(
        sum(
            max(int(quantity), 0)
            for troop_type, quantity in troop_quantities.items()
            if troop_type in balance.UNIT_CATALOG
        )
    )


__all__ = [
    "BALANCE_VERSION",
    "BASE_BUILDING_COSTS",
    "BASE_TROOP_COSTS",
    "BASE_TRAINING_TIMES",
    "STORAGE_BASE_CAPACITY",
    "STORAGE_PER_WAREHOUSE_LEVEL",
    "calculate_population_used",
    "enforce_storage_limits",
    "get_building_cost",
    "get_storage_capacity",
    "get_training_time",
    "get_troop_cost",
]
