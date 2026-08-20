"""Combat resolution helpers for calculating battle outcomes."""

import json
import math
import random
from typing import Dict, Tuple

from .. import models
from . import balance
from . import event as event_service

# Compatibility aliases. Canonical unit numbers live only in ``balance``.
UNIT_STATS = balance.unit_combat_stats_with_legacy_aliases()
WALL_NAME = balance.WALL_BUILDING_KEY
WALL_BONUS_PER_LEVEL = balance.WALL_BONUS_PER_LEVEL


def _wall_names() -> set[str]:
    return {balance.WALL_BUILDING_KEY, balance.LEGACY_WALL_BUILDING_NAME}


def _split_attack_by_type(
    troops: Dict[str, int], hero: models.Hero | None = None
) -> Tuple[Dict[str, float], float]:
    """Return attack totals split by troop category and total attack value."""

    attack_by_type = {"infantry": 0.0, "cavalry": 0.0, "siege": 0.0}
    total_attack = 0.0
    for unit, amount in troops.items():
        stats = UNIT_STATS.get(unit, None)
        if not stats:
            continue
        unit_attack = stats.get("attack", 0)
        attack_value = unit_attack * amount
        attack_by_type[stats["type"]] += attack_value
        total_attack += attack_value

    if hero and hero.status == "moving":
        hero_attack = 100 + (hero.attack_points * 10)
        attack_by_type["infantry"] += hero_attack
        total_attack += hero_attack

    return attack_by_type, total_attack


def _defense_values(
    defender_troops: Dict[str, int], hero: models.Hero | None = None
) -> Dict[str, float]:
    """Calculate defense values per troop category."""

    defenses = {"infantry": 0.0, "cavalry": 0.0, "siege": 0.0}
    for unit, amount in defender_troops.items():
        stats = UNIT_STATS.get(unit)
        if not stats:
            continue
        defenses["infantry"] += stats.get("def_inf", 0) * amount
        defenses["cavalry"] += stats.get("def_cav", 0) * amount
        defenses["siege"] += stats.get("def_siege", stats.get("def_inf", 0)) * amount

    if hero and hero.status == "home":
        hero_def = 100 + (hero.defense_points * 10)
        defenses["infantry"] += hero_def
        defenses["cavalry"] += hero_def
        defenses["siege"] += hero_def

    return defenses


def _wall_bonus(city: models.City) -> float:
    """Return defense multiplier provided by the canonical/legacy wall."""

    wall = next((b for b in city.buildings if b.name in _wall_names()), None)
    if not wall:
        return 1.0
    return 1.0 + wall.level * WALL_BONUS_PER_LEVEL


def _moral(attacker_strength: float, defender_strength: float) -> float:
    """Calculate morale based on attacker and defender strengths."""

    attacker_points = max(attacker_strength, 1)
    defender_points = max(defender_strength, 1)
    raw = math.sqrt(defender_points / attacker_points)
    return min(balance.MORALE_MAX, max(balance.MORALE_MIN, raw))


def _luck() -> float:
    """Return a random luck modifier inside the versioned balance limits."""

    return random.uniform(balance.LUCK_MIN, balance.LUCK_MAX)


def _weighted_defense(
    defenses: Dict[str, float],
    attack_distribution: Dict[str, float],
    wall_multiplier: float,
) -> float:
    """Weight defense by attack distribution and wall effects."""

    total_attack = sum(attack_distribution.values()) or 1
    ratios = {k: v / total_attack for k, v in attack_distribution.items()}
    defense_value = (
        defenses["infantry"] * ratios.get("infantry", 0)
        + defenses["cavalry"] * ratios.get("cavalry", 0)
        + defenses["siege"] * ratios.get("siege", 0)
    )
    return defense_value * wall_multiplier


def _loss_ratios(effective_attack: float, defense_value: float) -> Tuple[float, float]:
    """Determine attacker and defender loss ratios from strengths."""

    if effective_attack <= 0:
        return 1.0, 0.0
    if defense_value <= 0:
        return 0.0, 1.0

    decisive = balance.DECISIVE_STRENGTH_RATIO
    if effective_attack > defense_value * decisive:
        return (max(0.05, (defense_value / effective_attack) ** 0.5)), 1.0
    if defense_value > effective_attack * decisive:
        return 1.0, max(0.05, (effective_attack / defense_value) ** 0.5)

    balance_factor = effective_attack / defense_value
    attacker_ratio = min(1.0, (1 / balance_factor) ** 0.5)
    defender_ratio = min(1.0, balance_factor ** 0.5)
    return attacker_ratio, defender_ratio


def _apply_losses(troops: Dict[str, int], loss_ratio: float) -> Dict[str, int]:
    losses = {}
    for unit, amount in troops.items():
        losses[unit] = min(amount, int(round(amount * loss_ratio)))
    return losses


def _find_target_building(city: models.City, target_building: str):
    names = {target_building}
    if target_building in _wall_names():
        names = _wall_names()
    return next((building for building in city.buildings if building.name in names), None)


def resolve_battle(
    attacker_city: models.City,
    defender_city: models.City,
    attacking_troops: Dict[str, int],
    modifiers: Dict[str, float] | None = None,
    attacker_hero: models.Hero | None = None,
    target_building: str | None = None,
):
    """Resolve combat between attacking and defending cities."""

    modifiers = modifiers or event_service.DEFAULT_MODIFIERS
    defender_troops = {
        troop.unit_type: troop.quantity for troop in defender_city.troops
    }
    defender_hero = defender_city.owner.hero if defender_city.owner else None
    if defender_hero and defender_hero.city_id != defender_city.id:
        defender_hero = None

    attack_distribution, base_attack = _split_attack_by_type(
        attacking_troops, attacker_hero
    )
    defenses = _defense_values(defender_troops, defender_hero)
    wall_multiplier = _wall_bonus(defender_city)

    moral = _moral(base_attack, sum(defenses.values()))
    luck_factor = _luck()

    effective_attack = base_attack * moral * (1 + luck_factor)
    defense_value = _weighted_defense(
        defenses, attack_distribution, wall_multiplier
    )

    attacker_loss_ratio, defender_loss_ratio = _loss_ratios(
        effective_attack, defense_value
    )
    attacker_losses = _apply_losses(attacking_troops, attacker_loss_ratio)
    defender_losses = _apply_losses(defender_troops, defender_loss_ratio)

    if attacker_hero and attacker_loss_ratio > 0.9:
        attacker_hero.health = 0
        attacker_hero.status = "dead"
    elif attacker_hero:
        attacker_hero.health = max(
            0, attacker_hero.health - (attacker_loss_ratio * 100)
        )
        if attacker_hero.health <= 0:
            attacker_hero.status = "dead"

    if defender_hero and defender_loss_ratio > 0.9:
        defender_hero.health = 0
        defender_hero.status = "dead"
    elif defender_hero:
        defender_hero.health = max(
            0, defender_hero.health - (defender_loss_ratio * 100)
        )
        if defender_hero.health <= 0:
            defender_hero.status = "dead"

    attacker_points_gained = sum(defender_losses.values())
    defender_points_gained = sum(attacker_losses.values())

    xp_gained = 0
    if attacker_city.owner:
        attacker_city.owner.attacker_points += attacker_points_gained
        xp_gained = attacker_points_gained

    if defender_city.owner:
        defender_city.owner.defender_points += defender_points_gained
        if defender_hero and defender_hero.status != "dead":
            defender_hero.xp += defender_points_gained

    attacker_survivors = {
        unit: max(0, attacking_troops.get(unit, 0) - attacker_losses.get(unit, 0))
        for unit in attacking_troops
    }
    defender_survivors = {
        unit: max(0, defender_troops.get(unit, 0) - defender_losses.get(unit, 0))
        for unit in defender_troops
    }

    loot = {"wood": 0, "clay": 0, "iron": 0}
    if sum(defender_survivors.values()) == 0 and base_attack > 0:
        total_carry = 0
        for unit, amount in attacker_survivors.items():
            stats = UNIT_STATS.get(unit)
            if stats:
                total_carry += stats.get("carry", 0) * amount

        loot_modifier = max(float(modifiers.get("loot_modifier", 1.0)), 0.0)
        effective_carry = total_carry * loot_modifier
        available_wood = defender_city.wood
        available_clay = defender_city.clay
        available_iron = defender_city.iron
        total_resources = available_wood + available_clay + available_iron
        if total_resources > 0:
            take_ratio = min(1.0, effective_carry / total_resources)
            loot = {
                "wood": int(available_wood * take_ratio),
                "clay": int(available_clay * take_ratio),
                "iron": int(available_iron * take_ratio),
            }
            defender_city.wood -= loot["wood"]
            defender_city.clay -= loot["clay"]
            defender_city.iron -= loot["iron"]
            attacker_city.wood += loot["wood"]
            attacker_city.clay += loot["clay"]
            attacker_city.iron += loot["iron"]

    wall_damage = None
    building_damage = None
    loyalty_change = 0.0
    conquest = False

    if sum(defender_survivors.values()) == 0:
        siege_survivors = (
            attacker_survivors.get("quebramuros", 0)
            + attacker_survivors.get("ram", 0)
        )
        if siege_survivors > 0:
            wall = next(
                (b for b in defender_city.buildings if b.name in _wall_names()),
                None,
            )
            if wall and wall.level > 0:
                damage = max(1, int(siege_survivors**0.5))
                old_level = wall.level
                wall.level = max(0, wall.level - damage)
                wall_damage = (old_level, wall.level)

        catapult_survivors = attacker_survivors.get("catapult", 0)
        if catapult_survivors > 0 and target_building:
            target_b = _find_target_building(defender_city, target_building)
            if target_b and target_b.level > 0:
                catapult_damage = max(1, int(catapult_survivors**0.5))
                old_b_level = target_b.level
                target_b.level = max(0, target_b.level - catapult_damage)

                if target_b.name in _wall_names() and wall_damage:
                    wall_damage = (wall_damage[0], target_b.level)
                elif target_b.name in _wall_names():
                    wall_damage = (old_b_level, target_b.level)
                else:
                    building_damage = {
                        "building": target_building,
                        "old_level": old_b_level,
                        "new_level": target_b.level,
                    }

        nobles = attacker_survivors.get("noble", 0)
        if nobles > 0 and defender_city.owner_id is None:
            reduction = sum(
                random.randint(
                    balance.BARBARIAN_LOYALTY_DROP_MIN,
                    balance.BARBARIAN_LOYALTY_DROP_MAX,
                )
                for _ in range(nobles)
            )
            defender_city.loyalty -= reduction
            loyalty_change = reduction

            if defender_city.loyalty <= 0:
                conquest = True
                defender_city.owner_id = attacker_city.owner_id
                defender_city.loyalty = balance.BARBARIAN_CONQUEST_RESET_LOYALTY

    report = {
        "attacker_losses": attacker_losses,
        "defender_losses": defender_losses,
        "attacker_survivors": attacker_survivors,
        "defender_survivors": defender_survivors,
        "loot": loot,
        "wall_damage": wall_damage,
        "building_damage": building_damage,
        "loyalty_change": loyalty_change,
        "conquest": conquest,
        "moral": moral,
        "luck": luck_factor,
        "effective_attack": effective_attack,
        "defense_value": defense_value,
        "xp_gained": xp_gained,
    }
    return report


def build_battle_report_content(
    attacker_city: models.City,
    defender_city: models.City,
    battle_result: Dict,
) -> str:
    """Generate a JSON battle report for attacker and defender."""

    attacker_losses = battle_result.get("attacker_losses", {})
    defender_losses = battle_result.get("defender_losses", {})
    attacker_survivors = battle_result.get("attacker_survivors", {})
    defender_survivors = battle_result.get("defender_survivors", {})
    loot = battle_result.get("loot", {})
    wall_damage = battle_result.get("wall_damage")
    building_damage = battle_result.get("building_damage")
    loyalty_change = battle_result.get("loyalty_change", 0)
    conquest = battle_result.get("conquest", False)
    xp_gained = battle_result.get("xp_gained", 0)

    attacker_initial = {
        unit: attacker_survivors.get(unit, 0) + attacker_losses.get(unit, 0)
        for unit in set(attacker_survivors) | set(attacker_losses)
    }
    defender_initial = {
        unit: defender_survivors.get(unit, 0) + defender_losses.get(unit, 0)
        for unit in set(defender_survivors) | set(defender_losses)
    }

    report_data = {
        "type": "battle",
        "attacker": {
            "id": attacker_city.id,
            "name": attacker_city.name,
            "owner": attacker_city.owner.username if attacker_city.owner else "Bárbaros",
            "initial": attacker_initial,
            "losses": attacker_losses,
            "xp_gained": xp_gained,
        },
        "defender": {
            "id": defender_city.id,
            "name": defender_city.name,
            "owner": defender_city.owner.username if defender_city.owner else "Bárbaros",
            "initial": defender_initial,
            "losses": defender_losses,
        },
        "loot": loot,
        "wall_damage": wall_damage,
        "building_damage": building_damage,
        "loyalty_change": loyalty_change,
        "conquest": conquest,
        "moral": battle_result.get("moral"),
        "luck": battle_result.get("luck"),
        "effective_attack": battle_result.get("effective_attack"),
        "defense_value": battle_result.get("defense_value"),
    }

    return json.dumps(report_data)


def resolve_oasis_battle(
    attacker_city: models.City,
    oasis: models.Oasis,
    attacking_troops: Dict[str, int],
    modifiers: Dict[str, float] | None = None,
    attacker_hero: models.Hero | None = None,
):
    """Resolve combat between attacking city and a defending oasis."""

    modifiers = modifiers or event_service.DEFAULT_MODIFIERS
    defender_troops = oasis.troops or {}

    attack_distribution, base_attack = _split_attack_by_type(
        attacking_troops, attacker_hero
    )
    defenses = _defense_values(defender_troops, None)
    wall_multiplier = 1.0

    moral = 1.0
    luck_factor = _luck()

    effective_attack = base_attack * moral * (1 + luck_factor)
    defense_value = _weighted_defense(
        defenses, attack_distribution, wall_multiplier
    )

    attacker_loss_ratio, defender_loss_ratio = _loss_ratios(
        effective_attack, defense_value
    )
    attacker_losses = _apply_losses(attacking_troops, attacker_loss_ratio)
    defender_losses = _apply_losses(defender_troops, defender_loss_ratio)

    if attacker_hero and attacker_loss_ratio > 0.9:
        attacker_hero.health = 0
        attacker_hero.status = "dead"
    elif attacker_hero:
        attacker_hero.health = max(
            0, attacker_hero.health - (attacker_loss_ratio * 100)
        )
        if attacker_hero.health <= 0:
            attacker_hero.status = "dead"

    attacker_points_gained = sum(defender_losses.values())
    xp_gained = attacker_points_gained if attacker_city.owner else 0

    attacker_survivors = {
        unit: quantity - attacker_losses.get(unit, 0)
        for unit, quantity in attacking_troops.items()
    }
    defender_survivors = {
        unit: quantity - defender_losses.get(unit, 0)
        for unit, quantity in defender_troops.items()
    }

    return {
        "attacker_losses": attacker_losses,
        "defender_losses": defender_losses,
        "attacker_survivors": attacker_survivors,
        "defender_survivors": defender_survivors,
        "xp_gained": xp_gained,
        "loot": {},
        "conquered": (
            sum(defender_survivors.values()) == 0
            and attacker_hero
            and attacker_hero.health > 0
        ),
    }


def build_oasis_report_content(
    attacker_city: models.City,
    oasis: models.Oasis,
    battle_result: Dict,
) -> str:
    """Generate a JSON battle report for oasis combat."""

    attacker_losses = battle_result.get("attacker_losses", {})
    defender_losses = battle_result.get("defender_losses", {})
    attacker_survivors = battle_result.get("attacker_survivors", {})
    defender_survivors = battle_result.get("defender_survivors", {})
    conquest = battle_result.get("conquest", False)
    xp_gained = battle_result.get("xp_gained", 0)

    attacker_initial = {
        unit: attacker_survivors.get(unit, 0) + attacker_losses.get(unit, 0)
        for unit in set(attacker_survivors) | set(attacker_losses)
    }
    defender_initial = {
        unit: defender_survivors.get(unit, 0) + defender_losses.get(unit, 0)
        for unit in set(defender_survivors) | set(defender_losses)
    }

    report_data = {
        "type": "oasis_battle",
        "attacker": {
            "id": attacker_city.id,
            "name": attacker_city.name,
            "owner": attacker_city.owner.username if attacker_city.owner else "Bárbaros",
            "initial": attacker_initial,
            "losses": attacker_losses,
            "xp_gained": xp_gained,
        },
        "defender": {
            "id": oasis.id,
            "name": f"Oasis ({oasis.resource_type})",
            "owner": "Naturaleza",
            "initial": defender_initial,
            "losses": defender_losses,
        },
        "conquest": conquest,
        "loot": {},
        "moral": 1.0,
        "luck": 0.0,
    }

    return json.dumps(report_data)
