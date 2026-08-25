"""Canonical, independently versioned rules for the BM-0068 hero package."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .. import models

HERO_RULES_VERSION = "2026.08.25-bm0068-v1"
HERO_LEVEL_CAP = 100
HERO_POINTS_PER_LEVEL = 4
HERO_MAX_HEALTH = 100.0
HERO_MIN_ADVENTURE_HEALTH = 20.0
HERO_REVIVE_RESOURCE = "gold"
HERO_REVIVE_BASE_COST = 50
HERO_REVIVE_COST_PER_LEVEL = 10
HERO_REVIVE_HEALTH = 100.0
HERO_ADVENTURES_PER_BATCH = 3
HERO_MAX_DEFENSE_REDUCTION = 0.60
HERO_MAX_SPEED_REDUCTION = 0.50

ATTRIBUTE_EFFECTS = {
    "attack": {"per_point": 0.01, "effect": "adventure_xp_bonus"},
    "defense": {"per_point": 0.01, "effect": "adventure_damage_reduction"},
    "production": {"per_point": 0.005, "effect": "adventure_resource_bonus"},
}

ADVENTURE_DIFFICULTIES: dict[str, dict[str, Any]] = {
    "easy": {
        "duration_seconds": 300,
        "base_xp": 50,
        "damage_min": 1,
        "damage_max": 10,
        "resource_min": 100,
        "resource_max": 200,
    },
    "medium": {
        "duration_seconds": 1800,
        "base_xp": 200,
        "damage_min": 10,
        "damage_max": 30,
        "resource_min": 250,
        "resource_max": 500,
    },
    "hard": {
        "duration_seconds": 7200,
        "base_xp": 1000,
        "damage_min": 30,
        "damage_max": 60,
        "resource_min": 600,
        "resource_max": 1000,
    },
}
ADVENTURE_DIFFICULTY_PATTERN = ("easy", "easy", "medium", "medium", "hard")
ADVENTURE_ITEM_LOOT_CHANCE = 0.10
ADVENTURE_RESOURCE_LOOT_CHANCE = 0.30

ITEM_CATALOG: dict[str, dict[str, Any]] = {
    "wooden_sword": {
        "name": "Espada de Madera",
        "description": "Arma de entrenamiento que aumenta la experiencia de aventura.",
        "slot": "weapon",
        "rarity": "common",
        "bonus_type": "attack",
        "bonus_value": 0.05,
    },
    "leather_helmet": {
        "name": "Casco de Cuero",
        "description": "Protección básica que reduce el daño sufrido en aventuras.",
        "slot": "head",
        "rarity": "common",
        "bonus_type": "defense",
        "bonus_value": 0.05,
    },
    "travel_boots": {
        "name": "Botas de Viaje",
        "description": "Acortan el tiempo necesario para completar aventuras.",
        "slot": "feet",
        "rarity": "common",
        "bonus_type": "speed",
        "bonus_value": 0.10,
    },
    "war_axe": {
        "name": "Hacha de Guerra",
        "description": "Arma rara que aumenta la experiencia ganada en aventuras.",
        "slot": "weapon",
        "rarity": "rare",
        "bonus_type": "attack",
        "bonus_value": 0.15,
    },
    "plate_armor": {
        "name": "Armadura de Placas",
        "description": "Armadura épica que reduce el daño sufrido en aventuras.",
        "slot": "body",
        "rarity": "epic",
        "bonus_type": "defense",
        "bonus_value": 0.20,
    },
    "war_horse": {
        "name": "Caballo de Guerra",
        "description": "Montura épica que reduce la duración de las aventuras.",
        "slot": "horse",
        "rarity": "epic",
        "bonus_type": "speed",
        "bonus_value": 0.25,
    },
    "ancient_map": {
        "name": "Mapa Antiguo",
        "description": "Artefacto legendario que aumenta el botín de recursos.",
        "slot": "artifact",
        "rarity": "legendary",
        "bonus_type": "loot",
        "bonus_value": 0.20,
    },
}
ITEM_SLOT_ORDER = ("head", "body", "feet", "weapon", "horse", "artifact")


def revive_cost(level: int) -> int:
    return HERO_REVIVE_BASE_COST + max(int(level) - 1, 0) * HERO_REVIVE_COST_PER_LEVEL


def _decode_special_rules(raw: str | None) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {"legacy": text}
    return parsed if isinstance(parsed, dict) else {"legacy": parsed}


def pin_world_rules(world: models.World) -> bool:
    """Pin this package version in the world's durable rules manifest."""

    rules = _decode_special_rules(world.special_rules)
    section = rules.setdefault("hero_package", {})
    if not isinstance(section, dict):
        section = {}
        rules["hero_package"] = section
    existing = section.get("version")
    if existing not in (None, "", HERO_RULES_VERSION):
        raise RuntimeError(
            f"Unsupported hero package rules version for world {world.id}: {existing}"
        )
    before = world.special_rules or ""
    section["version"] = HERO_RULES_VERSION
    world.special_rules = json.dumps(rules, sort_keys=True, separators=(",", ":"))
    return world.special_rules != before


def world_rules_version(world: models.World) -> str:
    pin_world_rules(world)
    return HERO_RULES_VERSION


def snapshot() -> dict[str, Any]:
    return {
        "rules_version": HERO_RULES_VERSION,
        "level_cap": HERO_LEVEL_CAP,
        "points_per_level": HERO_POINTS_PER_LEVEL,
        "max_health": HERO_MAX_HEALTH,
        "min_adventure_health": HERO_MIN_ADVENTURE_HEALTH,
        "revive": {
            "resource": HERO_REVIVE_RESOURCE,
            "base_cost": HERO_REVIVE_BASE_COST,
            "cost_per_level": HERO_REVIVE_COST_PER_LEVEL,
            "health_after_revive": HERO_REVIVE_HEALTH,
        },
        "attribute_effects": deepcopy(ATTRIBUTE_EFFECTS),
        "adventures_per_batch": HERO_ADVENTURES_PER_BATCH,
        "adventure_difficulties": deepcopy(ADVENTURE_DIFFICULTIES),
        "loot": {
            "item_chance": ADVENTURE_ITEM_LOOT_CHANCE,
            "resource_chance": ADVENTURE_RESOURCE_LOOT_CHANCE,
            "none_chance": 1.0 - ADVENTURE_ITEM_LOOT_CHANCE - ADVENTURE_RESOURCE_LOOT_CHANCE,
        },
        "max_defense_reduction": HERO_MAX_DEFENSE_REDUCTION,
        "max_speed_reduction": HERO_MAX_SPEED_REDUCTION,
        "item_slots": list(ITEM_SLOT_ORDER),
        "item_catalog": deepcopy(ITEM_CATALOG),
        "claim_idempotent": True,
        "resource_rewards_respect_storage": True,
    }
