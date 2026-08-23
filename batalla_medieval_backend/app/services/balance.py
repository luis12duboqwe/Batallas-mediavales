"""Versioned, server-authoritative balance data for the live game.

BM-0040 establishes this module as the only place where gameplay balance
numbers are defined. Domain services may expose compatibility aliases, but
those aliases must point back to the objects in this module.

BM-0060 promotes the live resource model to wood, stone, iron and gold. The
legacy clay values are preserved 1:1 as stone by migration 0007. Gold is live
for production, storage, trade, transport and loot; final gold upkeep/costs are
owned by BM-0062/BM-0063 so this migration does not introduce a first-session
economic dead end.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Tuple

BALANCE_VERSION = "2026.08.23-bm0060.1"

RESOURCE_FIELDS = ("wood", "stone", "iron", "gold")
CITY_STARTING_RESOURCES: Dict[str, float] = {
    "wood": 500.0,
    "stone": 500.0,
    "iron": 500.0,
    "gold": 500.0,
}

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
    "town_hall": {"wood": 260.0, "stone": 200.0, "iron": 150.0},
    "barracks": {"wood": 200.0, "stone": 160.0, "iron": 170.0},
    "stable": {"wood": 320.0, "stone": 260.0, "iron": 260.0},
    "wall": {"wood": 100.0, "stone": 100.0, "iron": 50.0},
    "market": {"wood": 100.0, "stone": 100.0, "iron": 100.0},
    "farm": {"wood": 80.0, "stone": 80.0, "iron": 60.0},
    "warehouse": {"wood": 130.0, "stone": 100.0, "iron": 90.0},
    "smithy": {"wood": 220.0, "stone": 180.0, "iron": 240.0},
    "workshop": {"wood": 460.0, "stone": 510.0, "iron": 600.0},
    "world_wonder": {"wood": 10000.0, "stone": 10000.0, "iron": 10000.0},
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
# Economy / production / expansion
# ---------------------------------------------------------------------------

PRODUCTION_RATES_PER_HOUR: Dict[str, float] = {
    "wood": 15.0,
    "stone": 12.0,
    "iron": 10.0,
    "gold": 8.0,
}

STORAGE_BASE_CAPACITY = 5000.0
STORAGE_PER_WAREHOUSE_LEVEL = 2000.0
LOYALTY_MAX = 100.0
LOYALTY_RECOVERY_PER_HOUR = 2.0

CITY_FOUNDING_COST: Dict[str, float] = {
    "wood": 800.0,
    "stone": 800.0,
    "iron": 800.0,
}
CITY_INITIAL_LOYALTY = LOYALTY_MAX
STARTER_BUILDINGS = (
    {"name": "town_hall", "level": 1},
    {"name": "barracks", "level": 1},
)

# Tutorial is part of the accepted G2 economic path. Its completion reward is
# versioned here so the service, API/help and tests cannot silently diverge.
TUTORIAL_REWARD: Dict[str, float] = {
    "wood": 250.0,
    "stone": 250.0,
    "iron": 250.0,
    "gold": 250.0,
}

# The alpha PvE seed/AI values are versioned here because they directly affect
# tutorial difficulty, loot availability and recovery. BM-0067 may replace
# these values with the final barbarian/oasis model without creating a second
# source of truth.
BARBARIAN_STARTING_RESOURCES: Dict[str, float] = {
    "wood": 1000.0,
    "stone": 1000.0,
    "iron": 1000.0,
    "gold": 1000.0,
}
BARBARIAN_POPULATION_MAX = 100
BARBARIAN_STARTING_BUILDINGS = (
    ("town_hall", 1),
    ("barracks", 1),
    ("wall", 1),
)
BARBARIAN_STARTING_TROOPS = (
    ("basic_infantry", 20),
    ("archer", 10),
    ("spy", 2),
)
BARBARIAN_AI_BATCH_SIZE = 50
BARBARIAN_RESOURCE_GROWTH_CHANCE = 0.10
BARBARIAN_RESOURCE_GROWTH_AMOUNT = 10.0
BARBARIAN_RECRUIT_CHANCE = 0.05
BARBARIAN_RECRUIT_UNIT = "basic_infantry"

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

# BM-0063 owns the final upkeep numbers. Gold is already the canonical
# maintenance resource so no alternate resource model needs to be introduced.
UNIT_CATALOG: Dict[str, Dict[str, Any]] = {
    "basic_infantry": {
        "training_cost": {"wood": 50.0, "stone": 30.0, "iron": 20.0},
        "training_time_seconds": 45,
        "training_requirements": {"barracks": 1},
        "research_cost": {},
        "research_requirements": {},
        "researchable": False,
        "population": 1,
        "upkeep_per_hour": 0.0,
    },
    "heavy_infantry": {
        "training_cost": {"wood": 70.0, "stone": 60.0, "iron": 50.0},
        "training_time_seconds": 60,
        "training_requirements": {"barracks": 3, "smithy": 1},
        "research_cost": {"wood": 500.0, "stone": 400.0, "iron": 300.0},
        "research_requirements": {"barracks": 3},
        "researchable": True,
        "population": 1,
        "upkeep_per_hour": 0.0,
    },
    "archer": {
        "training_cost": {"wood": 80.0, "stone": 40.0, "iron": 40.0},
        "training_time_seconds": 50,
        "training_requirements": {"barracks": 5, "smithy": 3},
        "research_cost": {"wood": 600.0, "stone": 300.0, "iron": 300.0},
        "research_requirements": {"barracks": 5},
        "researchable": True,
        "population": 1,
        "upkeep_per_hour": 0.0,
    },
    "fast_cavalry": {
        "training_cost": {"wood": 120.0, "stone": 80.0, "iron": 100.0},
        "training_time_seconds": 70,
        "training_requirements": {"stable": 1},
        "research_cost": {"wood": 1000.0, "stone": 800.0, "iron": 600.0},
        "research_requirements": {"stable": 3},
        "researchable": True,
        "population": 1,
        "upkeep_per_hour": 0.0,
    },
    "heavy_cavalry": {
        "training_cost": {"wood": 200.0, "stone": 150.0, "iron": 200.0},
        "training_time_seconds": 80,
        "training_requirements": {"stable": 5, "smithy": 5},
        "research_cost": {"wood": 2000.0, "stone": 1500.0, "iron": 1500.0},
        "research_requirements": {"stable": 10},
        "researchable": True,
        "population": 1,
        "upkeep_per_hour": 0.0,
    },
    "spy": {
        "training_cost": {"wood": 40.0, "stone": 40.0, "iron": 40.0},
        "training_time_seconds": 30,
        "training_requirements": {"stable": 1},
        "research_cost": {"wood": 200.0, "stone": 200.0, "iron": 200.0},
        "research_requirements": {"stable": 1},
        "researchable": True,
        "population": 1,
        "upkeep_per_hour": 0.0,
    },
    "ram": {
        "training_cost": {"wood": 300.0, "stone": 200.0, "iron": 150.0},
        "training_time_seconds": 90,
        "training_requirements": {"workshop": 1},
        "research_cost": {"wood": 1500.0, "stone": 1000.0, "iron": 1000.0},
        "research_requirements": {"barracks": 10},
        "researchable": True,
        "population": 1,
        "upkeep_per_hour": 0.0,
    },
    "catapult": {
        "training_cost": {"wood": 350.0, "stone": 250.0, "iron": 300.0},
        "training_time_seconds": 120,
        "training_requirements": {"workshop": 5},
        "research_cost": {"wood": 2000.0, "stone": 1500.0, "iron": 1500.0},
        "research_requirements": {"barracks": 15},
        "researchable": True,
        "population": 1,
        "upkeep_per_hour": 0.0,
    },
    "noble": {
        "training_cost": {"wood": 1000.0, "stone": 1000.0, "iron": 1000.0},
        "training_time_seconds": 45,
        "training_requirements": {"town_hall": 20, "workshop": 10},
        "research_cost": {"wood": 10000.0, "stone": 10000.0, "iron": 10000.0},
        "research_requirements": {"town_hall": 20},
        "researchable": True,
        "population": 1,
        "upkeep_per_hour": 0.0,
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
    "basic_infantry": {
        "attack": 10,
        "def_inf": 20,
        "def_cav": 10,
        "def_siege": 20,
        "type": "infantry",
        "carry": 40,
    },
    "heavy_infantry": {
        "attack": 25,
        "def_inf": 40,
        "def_cav": 30,
        "def_siege": 40,
        "type": "infantry",
        "carry": 30,
    },
    "archer": {
        "attack": 30,
        "def_inf": 10,
        "def_cav": 40,
        "def_siege": 15,
        "type": "infantry",
        "carry": 35,
    },
    "fast_cavalry": {
        "attack": 60,
        "def_inf": 20,
        "def_cav": 20,
        "def_siege": 20,
        "type": "cavalry",
        "carry": 80,
    },
    "heavy_cavalry": {
        "attack": 100,
        "def_inf": 40,
        "def_cav": 60,
        "def_siege": 40,
        "type": "cavalry",
        "carry": 60,
    },
    "spy": {
        "attack": 0,
        "def_inf": 0,
        "def_cav": 0,
        "def_siege": 0,
        "type": "infantry",
        "carry": 0,
    },
    "ram": {
        "attack": 2,
        "def_inf": 40,
        "def_cav": 35,
        "def_siege": 60,
        "type": "siege",
        "carry": 0,
    },
    "catapult": {
        "attack": 2,
        "def_inf": 70,
        "def_cav": 70,
        "def_siege": 90,
        "type": "siege",
        "carry": 0,
    },
    "noble": {
        "attack": 30,
        "def_inf": 50,
        "def_cav": 50,
        "def_siege": 50,
        "type": "infantry",
        "carry": 0,
    },
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

# ---------------------------------------------------------------------------
# Combat / conquest / espionage
# ---------------------------------------------------------------------------

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

SPY_DEFENDER_OFFSET = 1.0
SPY_UNKNOWN_ATTACKER_CHANCE = 0.10
SPY_REVEALS_BUILDINGS_ON_SUCCESS = True

# ---------------------------------------------------------------------------
# Market / transport
# ---------------------------------------------------------------------------

MARKET_BUILDING_KEY = "market"
MERCHANT_CAPACITY_PER_LEVEL = 1000
TRANSPORT_BASE_SPEED = 1.0

# ---------------------------------------------------------------------------
# World events
# ---------------------------------------------------------------------------

EVENT_DEFAULT_MODIFIERS: Dict[str, float] = {
    "production_speed": 1.0,
    "troop_training_speed": 1.0,
    "movement_speed": 1.0,
    "spy_modifier": 1.0,
    "loot_modifier": 1.0,
}

EVENT_TEMPLATES: Dict[str, Tuple[str, str, Dict[str, float]]] = {
    "DOUBLE_RESOURCES": (
        "Doble de Recursos",
        "Los recursos producidos se duplican mientras dura el evento.",
        {"production_speed": 2.0},
    ),
    "STORM_EVENT": (
        "Tormenta",
        "Fuertes tormentas ralentizan todos los movimientos.",
        {"movement_speed": 0.5},
    ),
    "WAR_CRY": (
        "Grito de Guerra",
        "El entrenamiento de tropas es más rápido.",
        {"troop_training_speed": 0.8},
    ),
    "DARK_MOON": (
        "Luna Oscura",
        "Los espías son más efectivos, aumentando sus probabilidades de éxito.",
        {"spy_modifier": 1.2},
    ),
    "GLOBAL_TRIBUTE": (
        "Tributo Global",
        "Las victorias otorgan botín adicional.",
        {"loot_modifier": 1.2},
    ),
}


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

    events = {
        key: {
            "name": value[0],
            "description": value[1],
            "modifiers": deepcopy(value[2]),
        }
        for key, value in EVENT_TEMPLATES.items()
    }

    return {
        "version": BALANCE_VERSION,
        "resources": list(RESOURCE_FIELDS),
        "starting_resources": deepcopy(CITY_STARTING_RESOURCES),
        "buildings": {
            "catalog": buildings,
            "cost_growth": BUILDING_COST_GROWTH,
            "base_build_time_seconds": BASE_BUILD_TIME_SECONDS,
            "refund_factor": QUEUE_REFUND_FACTOR,
        },
        "units": {
            "catalog": units,
            "order": list(UNIT_ORDER),
            "maintenance_resource": "gold",
        },
        "production": {
            "base_rates_per_hour": deepcopy(PRODUCTION_RATES_PER_HOUR),
            "storage_base_capacity": STORAGE_BASE_CAPACITY,
            "storage_per_warehouse_level": STORAGE_PER_WAREHOUSE_LEVEL,
            "loyalty_max": LOYALTY_MAX,
            "loyalty_recovery_per_hour": LOYALTY_RECOVERY_PER_HOUR,
        },
        "expansion": {
            "founding_cost": deepcopy(CITY_FOUNDING_COST),
            "initial_loyalty": CITY_INITIAL_LOYALTY,
            "starter_buildings": deepcopy(list(STARTER_BUILDINGS)),
        },
        "tutorial": {
            "completion_reward": deepcopy(TUTORIAL_REWARD),
        },
        "pve_alpha": {
            "barbarian_starting_resources": deepcopy(BARBARIAN_STARTING_RESOURCES),
            "barbarian_population_max": BARBARIAN_POPULATION_MAX,
            "barbarian_starting_buildings": deepcopy(list(BARBARIAN_STARTING_BUILDINGS)),
            "barbarian_starting_troops": deepcopy(list(BARBARIAN_STARTING_TROOPS)),
            "barbarian_ai_batch_size": BARBARIAN_AI_BATCH_SIZE,
            "barbarian_resource_growth_chance": BARBARIAN_RESOURCE_GROWTH_CHANCE,
            "barbarian_resource_growth_amount": BARBARIAN_RESOURCE_GROWTH_AMOUNT,
            "barbarian_recruit_chance": BARBARIAN_RECRUIT_CHANCE,
            "barbarian_recruit_unit": BARBARIAN_RECRUIT_UNIT,
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
        "espionage": {
            "defender_offset": SPY_DEFENDER_OFFSET,
            "unknown_attacker_chance": SPY_UNKNOWN_ATTACKER_CHANCE,
            "reveals_buildings_on_success": SPY_REVEALS_BUILDINGS_ON_SUCCESS,
        },
        "market": {
            "building": MARKET_BUILDING_KEY,
            "merchant_capacity_per_level": MERCHANT_CAPACITY_PER_LEVEL,
            "transport_base_speed": TRANSPORT_BASE_SPEED,
        },
        "events": {
            "default_modifiers": deepcopy(EVENT_DEFAULT_MODIFIERS),
            "templates": events,
        },
    }
