"""Server-authoritative BM-0068 hero, item and adventure rules."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


HERO_RULES_VERSION = "2026.08.25-bm0068-v1"

HERO_MAX_LEVEL = 100
HERO_ATTRIBUTE_POINTS_PER_LEVEL = 4
HERO_MAX_HEALTH = 100.0
HERO_MIN_ADVENTURE_HEALTH = 20.0
HERO_ATTACK_BONUS_PER_POINT = 0.01
HERO_DEFENSE_BONUS_PER_POINT = 0.01
HERO_PRODUCTION_BONUS_PER_POINT = 0.005
HERO_REVIVE_COST_GOLD = 250.0
HERO_REVIVE_HEALTH = 50.0

HERO_EQUIPMENT_SLOTS = ("head", "body", "feet", "weapon", "horse", "artifact")
HERO_ITEM_RARITIES = ("common", "rare", "epic", "legendary")

# Preserve the existing progression curve, now behind a named versioned rule.
HERO_XP_TABLE = [0] + [int(100 * (1.2 ** (level - 1))) for level in range(1, HERO_MAX_LEVEL + 1)]

ADVENTURE_ACTIVE_OR_AVAILABLE_TARGET = 3
ADVENTURE_DIFFICULTY_WEIGHTS = ("easy", "easy", "medium", "medium", "hard")
ADVENTURE_CONFIG: dict[str, dict[str, Any]] = {
    "easy": {
        "duration": 300,
        "xp": 50,
        "damage_min": 1,
        "damage_max": 10,
        "resource_multiplier": 1,
    },
    "medium": {
        "duration": 1800,
        "xp": 200,
        "damage_min": 10,
        "damage_max": 30,
        "resource_multiplier": 3,
    },
    "hard": {
        "duration": 7200,
        "xp": 1000,
        "damage_min": 30,
        "damage_max": 60,
        "resource_multiplier": 10,
    },
}
ADVENTURE_ITEM_LOOT_CHANCE = 0.10
ADVENTURE_RESOURCE_LOOT_CHANCE = 0.30
ADVENTURE_RESOURCE_MIN_AMOUNT = 100
ADVENTURE_RESOURCE_MAX_AMOUNT = 500


def snapshot() -> dict[str, Any]:
    return {
        "rules_version": HERO_RULES_VERSION,
        "max_level": HERO_MAX_LEVEL,
        "attribute_points_per_level": HERO_ATTRIBUTE_POINTS_PER_LEVEL,
        "max_health": HERO_MAX_HEALTH,
        "min_adventure_health": HERO_MIN_ADVENTURE_HEALTH,
        "bonuses_per_point": {
            "attack": HERO_ATTACK_BONUS_PER_POINT,
            "defense": HERO_DEFENSE_BONUS_PER_POINT,
            "production": HERO_PRODUCTION_BONUS_PER_POINT,
        },
        "revive": {
            "resource": "gold",
            "cost": HERO_REVIVE_COST_GOLD,
            "health": HERO_REVIVE_HEALTH,
        },
        "equipment_slots": list(HERO_EQUIPMENT_SLOTS),
        "item_rarities": list(HERO_ITEM_RARITIES),
        "adventures": {
            "available_target": ADVENTURE_ACTIVE_OR_AVAILABLE_TARGET,
            "difficulty_weights": list(ADVENTURE_DIFFICULTY_WEIGHTS),
            "config": deepcopy(ADVENTURE_CONFIG),
            "item_loot_chance": ADVENTURE_ITEM_LOOT_CHANCE,
            "resource_loot_chance": ADVENTURE_RESOURCE_LOOT_CHANCE,
            "resource_amount_min": ADVENTURE_RESOURCE_MIN_AMOUNT,
            "resource_amount_max": ADVENTURE_RESOURCE_MAX_AMOUNT,
            "outcome_persisted": True,
            "retry_returns_same_result": True,
        },
    }
