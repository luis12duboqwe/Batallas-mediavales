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
HERO_MAX_ATTACK_BONUS = 0.50
HERO_MAX_DEFENSE_BONUS = 0.50
HERO_MAX_PRODUCTION_BONUS = 0.50
HERO_MAX_SPEED_BONUS = 0.50
HERO_REVIVE_COST_GOLD = 250.0
HERO_REVIVE_HEALTH = 50.0

HERO_EQUIPMENT_SLOTS = ("head", "body", "feet", "weapon", "horse", "artifact")
HERO_ITEM_RARITIES = ("common", "rare", "epic", "legendary")
HERO_ITEM_CATALOG: tuple[dict[str, Any], ...] = (
    {"name": "Espada de Madera", "slot": "weapon", "rarity": "common", "bonus_type": "attack_infantry", "bonus_value": 0.05, "description": "Una espada simple de entrenamiento."},
    {"name": "Casco de Cuero", "slot": "head", "rarity": "common", "bonus_type": "defense_infantry", "bonus_value": 0.05, "description": "Protección básica."},
    {"name": "Botas de Viaje", "slot": "feet", "rarity": "common", "bonus_type": "speed", "bonus_value": 0.10, "description": "Aumentan la velocidad de movimiento."},
    {"name": "Hacha de Guerra", "slot": "weapon", "rarity": "rare", "bonus_type": "attack_infantry", "bonus_value": 0.15, "description": "Un hacha afilada."},
    {"name": "Armadura de Placas", "slot": "body", "rarity": "epic", "bonus_type": "defense_infantry", "bonus_value": 0.20, "description": "Armadura pesada."},
    {"name": "Caballo de Guerra", "slot": "horse", "rarity": "epic", "bonus_type": "speed", "bonus_value": 0.25, "description": "Un corcel rápido y fuerte."},
    {"name": "Mapa Antiguo", "slot": "artifact", "rarity": "legendary", "bonus_type": "speed", "bonus_value": 0.50, "description": "Revela atajos secretos."},
)

HERO_XP_TABLE = [0] + [int(100 * (1.2 ** (level - 1))) for level in range(1, HERO_MAX_LEVEL + 1)]

ADVENTURE_ACTIVE_OR_AVAILABLE_TARGET = 3
ADVENTURE_DIFFICULTY_WEIGHTS = ("easy", "easy", "medium", "medium", "hard")
ADVENTURE_CONFIG: dict[str, dict[str, Any]] = {
    "easy": {"duration": 300, "xp": 50, "damage_min": 1, "damage_max": 10, "resource_multiplier": 1},
    "medium": {"duration": 1800, "xp": 200, "damage_min": 10, "damage_max": 30, "resource_multiplier": 3},
    "hard": {"duration": 7200, "xp": 1000, "damage_min": 30, "damage_max": 60, "resource_multiplier": 10},
}
ADVENTURE_ITEM_LOOT_CHANCE = 0.10
ADVENTURE_RESOURCE_LOOT_CHANCE = 0.30
ADVENTURE_RESOURCE_MIN_AMOUNT = 100
ADVENTURE_RESOURCE_MAX_AMOUNT = 500


def _equipped_bonus(hero, *bonus_types: str) -> float:
    if hero is None:
        return 0.0
    accepted = set(bonus_types)
    total = 0.0
    for item in getattr(hero, "items", ()) or ():
        if not getattr(item, "is_equipped", False):
            continue
        template = getattr(item, "template", None)
        if template is not None and getattr(template, "bonus_type", None) in accepted:
            total += max(float(getattr(template, "bonus_value", 0.0) or 0.0), 0.0)
    return total


def _attack_attribute_bonus(hero) -> float:
    if hero is None or float(getattr(hero, "health", 0.0)) <= 0:
        return 0.0
    return max(int(getattr(hero, "attack_points", 0)), 0) * HERO_ATTACK_BONUS_PER_POINT


def _defense_attribute_bonus(hero) -> float:
    if hero is None or float(getattr(hero, "health", 0.0)) <= 0:
        return 0.0
    return max(int(getattr(hero, "defense_points", 0)), 0) * HERO_DEFENSE_BONUS_PER_POINT


def attack_bonus_for_category(hero, category: str) -> float:
    """Return the bounded attack bonus that applies to one troop category."""

    if hero is None or float(getattr(hero, "health", 0.0)) <= 0:
        return 0.0
    normalized = str(category).strip().lower()
    value = _attack_attribute_bonus(hero)
    value += _equipped_bonus(hero, "attack_all", f"attack_{normalized}")
    return min(value, HERO_MAX_ATTACK_BONUS)


def defense_bonus_for_category(hero, category: str) -> float:
    """Return the bounded defense bonus against one troop category."""

    if hero is None or float(getattr(hero, "health", 0.0)) <= 0:
        return 0.0
    normalized = str(category).strip().lower()
    value = _defense_attribute_bonus(hero)
    value += _equipped_bonus(hero, "defense_all", f"defense_{normalized}")
    return min(value, HERO_MAX_DEFENSE_BONUS)


def attack_bonus(hero) -> float:
    """Compatibility scalar for the infantry attack path and legacy reports."""

    return attack_bonus_for_category(hero, "infantry")


def defense_bonus(hero) -> float:
    """Compatibility scalar for the infantry defense path and legacy reports."""

    return defense_bonus_for_category(hero, "infantry")


def attack_bonuses(hero) -> dict[str, float]:
    return {
        category: attack_bonus_for_category(hero, category)
        for category in ("infantry", "cavalry", "siege")
    }


def defense_bonuses(hero) -> dict[str, float]:
    return {
        category: defense_bonus_for_category(hero, category)
        for category in ("infantry", "cavalry", "siege")
    }


def production_bonus(hero) -> float:
    if hero is None or getattr(hero, "status", None) != "home" or float(getattr(hero, "health", 0.0)) <= 0:
        return 0.0
    value = max(int(getattr(hero, "production_points", 0)), 0) * HERO_PRODUCTION_BONUS_PER_POINT
    value += _equipped_bonus(hero, "production")
    return min(value, HERO_MAX_PRODUCTION_BONUS)


def speed_bonus(hero) -> float:
    if hero is None or float(getattr(hero, "health", 0.0)) <= 0:
        return 0.0
    return min(_equipped_bonus(hero, "speed"), HERO_MAX_SPEED_BONUS)


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
        "bonus_caps": {
            "attack": HERO_MAX_ATTACK_BONUS,
            "defense": HERO_MAX_DEFENSE_BONUS,
            "production": HERO_MAX_PRODUCTION_BONUS,
            "speed": HERO_MAX_SPEED_BONUS,
        },
        "revive": {"resource": "gold", "cost": HERO_REVIVE_COST_GOLD, "health": HERO_REVIVE_HEALTH},
        "equipment_slots": list(HERO_EQUIPMENT_SLOTS),
        "item_rarities": list(HERO_ITEM_RARITIES),
        "item_catalog": deepcopy(list(HERO_ITEM_CATALOG)),
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
