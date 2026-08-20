"""Versioned, server-authoritative balance data for the live game.

BM-0040 establishes this module as the only place where gameplay balance
numbers are defined. Domain services may expose compatibility aliases, but
those aliases must point back to the objects in this module.

The values in this first version deliberately preserve the behaviour used by
the accepted G2/G3 gameplay services. This change removes contradictory tables;
it does not perform a rebalance.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

BALANCE_VERSION = "2026.08.20-bm0040.1"

RESOURCE_FIELDS = ("wood", "clay", "iron")

# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------

BUILDING_ORDER = [
    "town_hall",
    "barracks",
    "stable",
    "wall",
    "market",
    "farm",
    "warehouse",
    "smithy",
    "workshop",
    "world_wonder",
]

BUILDING_DISPLAY_NAMES = {
    "town_hall": "Casa Central",
    "barracks": "Barracas",
    "stable": "Establos Imperiales",
    "wall": "Muralla de Guardia",
    "market": "Plaza Comercial",
    "farm": "Hacienda",
    "warehouse": "Gran Depósito",
    "smithy": "Forja Bélica",
    "workshop": "Taller de Asedio",
    "world_wonder": "Maravilla del Mundo",
}

BUILDING_COSTS: Dict[str, Dict[str, float]] = {
    "town_hall": {"wood": 260.0, "clay": 200.0, "iron": 150.0},
    "barracks": {"wood": 200.0, "clay": 160.0, "iron": 170.0},
    "stable": {"wood": 320.0, "clay": 260.0, "iron": 260.0},
    "wall": {"wood": 100.0, "clay": 100.0, "iron": 50.0},
    "market": {"wood": 100.0, "clay": 100.0, "iron": 100.0},
    "farm": {"wood": 80.0, "clay": 80.0, "iron": 60.0},
    "warehouse": {"wood": 130.0, "clay": 100.0, "iron": 90.0},
    "smithy": {"wood": 220.0, "clay": 180.0, "iron": 240.0},
    "workshop": {"wood": 460.0, "clay": 510.0, "iron": 600.0},
    "world_wonder": {"wood": 10000.0, "clay": 10000.0, "iron": 10000.0},
}

BUILDING_PREREQUISITES: Dict[str, Dict[str, int]] = {
    "stable": {"barracks": 5, "town_hall": 3},
    "market": {"warehouse": 1, "town_hall": 2},
    "wall": {"barracks": 1},
    "smithy": {"town_hall": 5, "barracks": 1},
    "workshop": {"town_hall": 10, "stable": 10},
    "world_wonder": {"town_hall": 20, "warehouse": 20},
}

BUILDING_COST_GROWTH = 1.20
BASE_BUILD_TIME_SECONDS = 420
QUEUE_REFUND_FACTOR = 0.80

# ---------------------------------------------------------------------------
# Economy / production
# ---------------------------------------------------------------------------

PRODUCTION_RATES_PER_HOUR: Dict[str, float] = {
    "wood": 15.0,
    "clay": 12.0,
    "iron": 10.0,
}

STORAGE_BASE_CAPACITY = 5000.0
STORAGE_PER_WAREHOUSE_LEVEL = 2000.0
LOYALTY_RECOVERY_PER_HOUR = 2.0

# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

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

UNIT_DISPLAY_NAMES = {
    "basic_infantry": "Lancero Común",
    "heavy_infantry": "Soldado de Acero",
    "archer": "Arquero Real",
    "fast_cavalry": "Jinete Explorador",
    "heavy_cavalry": "Caballero Imperial",
    "spy": "Infiltrador",
    "ram": "Quebramuros",
    "catapult": "Tormenta de Piedra",
    "noble": "Noble",
}

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

UNIT_SPEED: Dict[str, float] = {
    "basic_infantry": 0.60,
    "heavy_infantry": 0.55,
    "archer": 0.70,
    "fast_cavalry": 1.20,
    "heavy_cavalry": 0.90,
    "spy": 1.50,
    "ram": 0.50,
    "catapult": 0.45,
    "noble": 0.40,
}

UNIT_COMBAT_STATS: Dict[str, Dict[str, Any]] = {
    "basic_infantry": {"attack": 10, "def_inf": 20, "def_cav": 10, "def_siege": 20, "type": "infantry", "carry": 40},
    "heavy_infantry": {"attack": 25, "def_inf": 40, "def_cav": 30, "def_siege": 40, "type": "infantry", "carry": 30},
    "archer": {"attack": 30, "def_inf": 10, "def_cav": 40, "def_siege": 15, "type": "infantry", "carry": 35},
    "fast_cavalry": {"attack": 60, "def_inf": 20, "def_cav": 20, "def_siege": 20, "type": "cavalry", "carry": 80},
    "heavy_cavalry": {"attack": 100, "def_inf": 40, "def_cav": 60, "def_siege": 40, "type": "cavalry", "carry": 60},
    "spy": {"attack": 0, "def_inf": 0, "def_cav": 0, "def_siege": 0, "type": "infantry", "carry": 0},
    "ram": {"attack": 2, "def_inf": 40, "def_cav": 35, "def_siege": 60, "type": "siege", "carry": 0},
    "catapult": {"attack": 2, "def_inf": 70, "def_cav": 70, "def_siege": 90, "type": "siege", "carry": 0},
    "noble": {"attack": 30, "def_inf": 50, "def_cav": 50, "def_siege": 50, "type": "infantry", "carry": 0},
}

LEGACY_UNIT_ALIASES = {
    "lancero_comun": "basic_infantry",
    "soldado_de_acero": "heavy_infantry",
    "arquero_real": "archer",
    "jinete_explorador": "fast_cavalry",
    "caballero_imperial": "heavy_cavalry",
    "infiltrador": "spy",
    "quebramuros": "ram",
    "tormenta_de_piedra": "catapult",
}

# Combat-wide rules used by the accepted live resolver.
WALL_BUILDING_KEY = "wall"
LEGACY_WALL_BUILDING_NAME = "Muralla de Guardia"
WALL_BONUS_PER_LEVEL = 0.05
MORALE_MIN = 0.30
MORALE_MAX = 1.50
LUCK_MIN = -0.25
LUCK_MAX = 0.25
DECISIVE_STRENGTH_RATIO = 1.20
BARBARIAN_LOYALTY_DROP_MIN = 20
BARBARIAN_LOYALTY_DROP_MAX = 35
BARBARIAN_CONQUEST_RESET_LOYALTY = 25.0

# Market / transport rules.
MARKET_BUILDING_KEY = "market"
MERCHANT_CAPACITY_PER_LEVEL = 1000
TRANSPORT_BASE_SPEED = 1.0


def unit_combat_stats_with_legacy_aliases() -> Dict[str, Dict[str, Any]]:
    """Return combat stats including read-only legacy unit identifiers."""

    result = {key: deepcopy(value) for key, value in UNIT_COMBAT_STATS.items()}
    for legacy_name, canonical_name in LEGACY_UNIT_ALIASES.items():
        result[legacy_name] = deepcopy(UNIT_COMBAT_STATS[canonical_name])
    return result


def get_storage_capacity(warehouse_level: int) -> float:
    level = max(int(warehouse_level), 0)
    return STORAGE_BASE_CAPACITY + STORAGE_PER_WAREHOUSE_LEVEL * level


def get_building_cost(building_type: str, target_level: int) -> Dict[str, float]:
    if target_level < 1:
        raise ValueError("Target building level must be at least 1")
    base = BUILDING_COSTS.get(building_type)
    if base is None:
        raise ValueError(f"Unknown building type: {building_type}")
    multiplier = BUILDING_COST_GROWTH ** (target_level - 1)
    return {resource: float(value * multiplier) for resource, value in base.items()}


def snapshot() -> Dict[str, Any]:
    """Return the stable serializable contract consumed by APIs and UI."""

    units: Dict[str, Dict[str, Any]] = {}
    for unit_type in UNIT_ORDER:
        units[unit_type] = {
            "display_name": UNIT_DISPLAY_NAMES[unit_type],
            **deepcopy(UNIT_CATALOG[unit_type]),
            "movement_speed": UNIT_SPEED[unit_type],
            "combat": deepcopy(UNIT_COMBAT_STATS[unit_type]),
        }

    buildings: Dict[str, Dict[str, Any]] = {}
    for building_type in BUILDING_ORDER:
        buildings[building_type] = {
            "display_name": BUILDING_DISPLAY_NAMES[building_type],
            "base_cost": deepcopy(BUILDING_COSTS[building_type]),
            "requirements": deepcopy(BUILDING_PREREQUISITES.get(building_type, {})),
        }

    return {
        "version": BALANCE_VERSION,
        "resources": list(RESOURCE_FIELDS),
        "buildings": {
            "catalog": buildings,
            "cost_growth": BUILDING_COST_GROWTH,
            "base_build_time_seconds": BASE_BUILD_TIME_SECONDS,
            "refund_factor": QUEUE_REFUND_FACTOR,
        },
        "units": {"catalog": units, "order": list(UNIT_ORDER)},
        "production": {
            "base_rates_per_hour": deepcopy(PRODUCTION_RATES_PER_HOUR),
            "storage_base_capacity": STORAGE_BASE_CAPACITY,
            "storage_per_warehouse_level": STORAGE_PER_WAREHOUSE_LEVEL,
            "loyalty_recovery_per_hour": LOYALTY_RECOVERY_PER_HOUR,
        },
        "combat": {
            "wall_building": WALL_BUILDING_KEY,
            "wall_bonus_per_level": WALL_BONUS_PER_LEVEL,
            "morale_min": MORALE_MIN,
            "morale_max": MORALE_MAX,
            "luck_min": LUCK_MIN,
            "luck_max": LUCK_MAX,
            "decisive_strength_ratio": DECISIVE_STRENGTH_RATIO,
            "barbarian_loyalty_drop_min": BARBARIAN_LOYALTY_DROP_MIN,
            "barbarian_loyalty_drop_max": BARBARIAN_LOYALTY_DROP_MAX,
            "barbarian_conquest_reset_loyalty": BARBARIAN_CONQUEST_RESET_LOYALTY,
        },
        "market": {
            "building": MARKET_BUILDING_KEY,
            "merchant_capacity_per_level": MERCHANT_CAPACITY_PER_LEVEL,
            "transport_base_speed": TRANSPORT_BASE_SPEED,
        },
    }
