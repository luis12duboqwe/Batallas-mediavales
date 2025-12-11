"""
Economic balance utilities for buildings, troops, storage and population.

This module centralizes the economic formulas so that other services
(building, troop, movement, etc.) can reuse the same values.
"""
from __future__ import annotations

from typing import Dict, Mapping

# ------------------------------
# Base definitions
# ------------------------------

# Base construction cost for every building (level 1).
BASE_BUILDING_COSTS: Dict[str, Dict[str, float]] = {
    "Casa Central": {"wood": 200.0, "clay": 150.0, "iron": 100.0},
    "Aserradero": {"wood": 100.0, "clay": 50.0, "iron": 30.0},
    "Cantera de Ladrillo": {"wood": 80.0, "clay": 120.0, "iron": 40.0},
    "Mina Profunda": {"wood": 70.0, "clay": 80.0, "iron": 150.0},
    "Hacienda": {"wood": 150.0, "clay": 100.0, "iron": 70.0},
    "Gran Depósito": {"wood": 130.0, "clay": 180.0, "iron": 90.0},
    "Barracas": {"wood": 160.0, "clay": 120.0, "iron": 140.0},
    "Establos Imperiales": {"wood": 220.0, "clay": 180.0, "iron": 200.0},
    "Forja Bélica": {"wood": 250.0, "clay": 200.0, "iron": 220.0},
    "Muralla de Guardia": {"wood": 200.0, "clay": 250.0, "iron": 180.0},
    "Plaza Comercial": {"wood": 140.0, "clay": 140.0, "iron": 120.0},
    "Comandancia Militar": {"wood": 300.0, "clay": 260.0, "iron": 260.0},
}

# Base recruitment cost and population usage for each troop type.
BASE_TROOP_COSTS: Dict[str, Dict[str, float]] = {
    "Lancero Común": {"wood": 50.0, "clay": 30.0, "iron": 10.0, "population": 1.0},
    "Soldado de Acero": {"wood": 80.0, "clay": 60.0, "iron": 30.0, "population": 1.0},
    "Arquero Real": {"wood": 70.0, "clay": 40.0, "iron": 40.0, "population": 1.0},
    "Jinete Explorador": {"wood": 120.0, "clay": 80.0, "iron": 60.0, "population": 2.0},
    "Caballero Imperial": {"wood": 200.0, "clay": 160.0, "iron": 180.0, "population": 3.0},
    "Infiltrador": {"wood": 60.0, "clay": 60.0, "iron": 60.0, "population": 1.0},
    "Quebramuros": {"wood": 300.0, "clay": 240.0, "iron": 200.0, "population": 3.0},
    "Tormenta de Piedra": {"wood": 320.0, "clay": 280.0, "iron": 300.0, "population": 4.0},
}

# Base training times in seconds when the producing building is level 1.
BASE_TRAINING_TIMES: Dict[str, float] = {
    "Lancero Común": 30.0,
    "Soldado de Acero": 40.0,
    "Arquero Real": 45.0,
    "Jinete Explorador": 60.0,
    "Caballero Imperial": 90.0,
    "Infiltrador": 35.0,
    "Quebramuros": 110.0,
    "Tormenta de Piedra": 130.0,
}

# ------------------------------
# Economic formulas
# ------------------------------


def get_building_cost(building_type: str, level: int) -> Dict[str, float]:
    """
    Calculate the resource cost to build or upgrade a building to a given level.

    Formula: cost = base_cost * (1.26 ** (level - 1))
    """
    if level < 1:
        raise ValueError("Building level must be >= 1")

    base_cost = BASE_BUILDING_COSTS.get(building_type)
    if not base_cost:
        raise KeyError(f"Unknown building type: {building_type}")

    multiplier = 1.26 ** (level - 1)
    return {resource: value * multiplier for resource, value in base_cost.items()}


def get_troop_cost(troop_type: str, amount: int = 1) -> Dict[str, float]:
    """
    Calculate the total cost for training a number of troops (including population).
    """
    if amount < 1:
        raise ValueError("Amount of troops must be >= 1")

    base_cost = BASE_TROOP_COSTS.get(troop_type)
    if not base_cost:
        raise KeyError(f"Unknown troop type: {troop_type}")

    return {resource: value * amount for resource, value in base_cost.items()}


def get_training_time(troop_type: str, building_level: int) -> float:
    """
    Calculate training time in seconds for a troop type at a given training building level.

    Formula: time = base_time * (1.18 ** (building_level - 1))
    """
    if building_level < 1:
        raise ValueError("Building level must be >= 1")

    base_time = BASE_TRAINING_TIMES.get(troop_type)
    if base_time is None:
        raise KeyError(f"Unknown troop type: {troop_type}")

    return base_time * (1.18 ** (building_level - 1))


# ------------------------------
# Storage and population helpers
# ------------------------------

STORAGE_BASE_CAPACITY = 5000.0
STORAGE_GROWTH = 1.32
POPULATION_BASE = 50.0
POPULATION_GROWTH = 1.22


def get_storage_capacity(gran_deposito_level: int) -> float:
    """Return total resource capacity based on Gran Depósito level."""
    if gran_deposito_level < 1:
        return 0.0
    return STORAGE_BASE_CAPACITY * (STORAGE_GROWTH ** (gran_deposito_level - 1))


def enforce_storage_limits(resources: Mapping[str, float], storage_level: int) -> Dict[str, float]:
    """Clamp resource dictionary to the storage capacity of the given Gran Depósito level."""
    capacity = get_storage_capacity(storage_level)
    return {
        resource: min(amount, capacity)
        for resource, amount in resources.items()
    }


def get_population_capacity(hacienda_level: int) -> float:
    """Maximum population supported by the Hacienda level."""
    if hacienda_level < 1:
        return 0.0
    return POPULATION_BASE * (POPULATION_GROWTH ** (hacienda_level - 1))


def calculate_population_used(troop_quantities: Mapping[str, int]) -> float:
    """Total population consumed by the provided troop quantities."""
    population = 0.0
    for troop_type, quantity in troop_quantities.items():
        troop_cost = BASE_TROOP_COSTS.get(troop_type)
        if troop_cost:
            population += troop_cost.get("population", 0) * quantity
    return population


__all__ = [
    "BASE_BUILDING_COSTS",
    "BASE_TROOP_COSTS",
    "BASE_TRAINING_TIMES",
    "calculate_population_used",
    "enforce_storage_limits",
    "get_building_cost",
    "get_population_capacity",
    "get_storage_capacity",
    "get_training_time",
    "get_troop_cost",
]
