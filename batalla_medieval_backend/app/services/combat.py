"""Combat resolution helpers for calculating battle outcomes."""

import math
import random
import json
from typing import Dict, Tuple

from .. import models
from . import event as event_service

UNIT_STATS: Dict[str, Dict[str, float]] = {
    "lancero_comun": {"attack": 10, "def_inf": 20, "def_cav": 10, "def_siege": 20, "type": "infantry", "carry": 40},
    "soldado_de_acero": {"attack": 25, "def_inf": 40, "def_cav": 30, "def_siege": 40, "type": "infantry", "carry": 30},
    "arquero_real": {"attack": 30, "def_inf": 10, "def_cav": 40, "def_siege": 15, "type": "infantry", "carry": 35},
    "jinete_explorador": {"attack": 60, "def_inf": 20, "def_cav": 20, "def_siege": 20, "type": "cavalry", "carry": 80},
    "caballero_imperial": {"attack": 100, "def_inf": 40, "def_cav": 60, "def_siege": 40, "type": "cavalry", "carry": 60},
    "infiltrador": {"attack": 0, "def_inf": 0, "def_cav": 0, "def_siege": 0, "type": "infantry", "carry": 0},
    "quebramuros": {"attack": 2, "def_inf": 40, "def_cav": 35, "def_siege": 60, "type": "siege", "carry": 0},
    "tormenta_de_piedra": {"attack": 2, "def_inf": 70, "def_cav": 70, "def_siege": 90, "type": "siege", "carry": 0},
    "noble": {"attack": 30, "def_inf": 50, "def_cav": 50, "def_siege": 50, "type": "infantry", "carry": 0},
    # Aliases for backwards compatibility with previous unit naming
    "basic_infantry": {"attack": 10, "def_inf": 20, "def_cav": 10, "def_siege": 20, "type": "infantry", "carry": 40},
    "heavy_infantry": {"attack": 25, "def_inf": 40, "def_cav": 30, "def_siege": 40, "type": "infantry", "carry": 30},
    "archer": {"attack": 30, "def_inf": 10, "def_cav": 40, "def_siege": 15, "type": "infantry", "carry": 35},
    "fast_cavalry": {"attack": 60, "def_inf": 20, "def_cav": 20, "def_siege": 20, "type": "cavalry", "carry": 80},
    "heavy_cavalry": {"attack": 100, "def_inf": 40, "def_cav": 60, "def_siege": 40, "type": "cavalry", "carry": 60},
    "spy": {"attack": 0, "def_inf": 0, "def_cav": 0, "def_siege": 0, "type": "infantry", "carry": 0},
    "ram": {"attack": 2, "def_inf": 40, "def_cav": 35, "def_siege": 60, "type": "siege", "carry": 0},
    "catapult": {"attack": 2, "def_inf": 70, "def_cav": 70, "def_siege": 90, "type": "siege", "carry": 0},
}

WALL_NAME = "Muralla de Guardia"
WALL_BONUS_PER_LEVEL = 0.05


def _split_attack_by_type(troops: Dict[str, int], hero: models.Hero | None = None) -> Tuple[Dict[str, float], float]:
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
        # Hero bonus: 100 base + 10 per attack point
        hero_attack = 100 + (hero.attack_points * 10)
        # Hero counts as infantry for now
        attack_by_type["infantry"] += hero_attack
        total_attack += hero_attack

    return attack_by_type, total_attack


def _defense_values(defender_troops: Dict[str, int], hero: models.Hero | None = None) -> Dict[str, float]:
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
        # Hero bonus: 100 base + 10 per defense point
        hero_def = 100 + (hero.defense_points * 10)
        defenses["infantry"] += hero_def
        defenses["cavalry"] += hero_def
        defenses["siege"] += hero_def

    return defenses


def _wall_bonus(city: models.City) -> float:
    """Return defense multiplier provided by the wall level."""

    wall = next((b for b in city.buildings if b.name == WALL_NAME), None)
    if not wall:
        return 1.0
    return 1.0 + wall.level * WALL_BONUS_PER_LEVEL


def _moral(attacker_strength: float, defender_strength: float) -> float:
    """Calculate morale based on attacker and defender strengths."""

    attacker_points = max(attacker_strength, 1)
    defender_points = max(defender_strength, 1)
    return min(1.5, max(0.3, math.sqrt(defender_points / attacker_points)))


def _luck() -> float:
    """Return a random luck modifier."""

    return random.uniform(-0.25, 0.25)


def _weighted_defense(
    defenses: Dict[str, float], attack_distribution: Dict[str, float], wall_multiplier: float
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

    if effective_attack > defense_value * 1.2:
        return (max(0.05, (defense_value / effective_attack) ** 0.5)), 1.0
    if defense_value > effective_attack * 1.2:
        return 1.0, max(0.05, (effective_attack / defense_value) ** 0.5)

    balance_factor = effective_attack / defense_value
    attacker_ratio = min(1.0, (1 / balance_factor) ** 0.5)
    defender_ratio = min(1.0, balance_factor ** 0.5)
    return attacker_ratio, defender_ratio


def _apply_losses(troops: Dict[str, int], loss_ratio: float) -> Dict[str, int]:
    """Return troop losses by unit using a given ratio."""

    losses = {}
    for unit, amount in troops.items():
        losses[unit] = min(amount, int(round(amount * loss_ratio)))
    return losses


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
    defender_troops = {troop.unit_type: troop.quantity for troop in defender_city.troops}
    defender_hero = defender_city.owner.hero if defender_city.owner else None
    if defender_hero and defender_hero.city_id != defender_city.id:
        defender_hero = None # Hero not in city

    attack_distribution, base_attack = _split_attack_by_type(attacking_troops, attacker_hero)
    defenses = _defense_values(defender_troops, defender_hero)
    wall_multiplier = _wall_bonus(defender_city)

    moral = _moral(base_attack, sum(defenses.values()))
    luck_factor = _luck()

    effective_attack = base_attack * moral * (1 + luck_factor)
    defense_value = _weighted_defense(defenses, attack_distribution, wall_multiplier)

    attacker_loss_ratio, defender_loss_ratio = _loss_ratios(effective_attack, defense_value)
    attacker_losses = _apply_losses(attacking_troops, attacker_loss_ratio)
    defender_losses = _apply_losses(defender_troops, defender_loss_ratio)

    # Hero damage logic
    if attacker_hero and attacker_loss_ratio > 0.9:
        attacker_hero.health = 0
        attacker_hero.status = "dead"
    elif attacker_hero:
        attacker_hero.health = max(0, attacker_hero.health - (attacker_loss_ratio * 100))
        if attacker_hero.health <= 0:
            attacker_hero.status = "dead"
            
    if defender_hero and defender_loss_ratio > 0.9:
        defender_hero.health = 0
        defender_hero.status = "dead"
    elif defender_hero:
        defender_hero.health = max(0, defender_hero.health - (defender_loss_ratio * 100))
        if defender_hero.health <= 0:
            defender_hero.status = "dead"

    # Ranking points
    attacker_points_gained = sum(defender_losses.values()) # Simplified: 1 point per unit
    defender_points_gained = sum(attacker_losses.values())
    
    xp_gained = 0
    if attacker_city.owner:
        attacker_city.owner.attacker_points += attacker_points_gained
        xp_gained = attacker_points_gained

    if defender_city.owner:
        defender_city.owner.defender_points += defender_points_gained
        if defender_hero and defender_hero.status != "dead":
             defender_hero.xp += defender_points_gained

    attacker_survivors = {u: max(0, attacking_troops.get(u, 0) - attacker_losses.get(u, 0)) for u in attacking_troops}
    defender_survivors = {u: max(0, defender_troops.get(u, 0) - defender_losses.get(u, 0)) for u in defender_troops}

    # Loot Logic
    loot = {"wood": 0, "clay": 0, "iron": 0}
    if sum(defender_survivors.values()) == 0 and base_attack > 0:
        # Calculate total carry capacity
        total_carry = 0
        for unit, amount in attacker_survivors.items():
            stats = UNIT_STATS.get(unit)
            if stats:
                total_carry += stats.get("carry", 0) * amount
        
        # Available resources
        available_wood = defender_city.wood
        available_clay = defender_city.clay
        available_iron = defender_city.iron
        
        # Simple distribution: take proportional to what is available
        total_resources = available_wood + available_clay + available_iron
        if total_resources > 0:
            take_ratio = min(1.0, total_carry / total_resources)
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

    # Siege & Loyalty Logic
    wall_damage = None
    building_damage = None
    loyalty_change = 0.0
    conquest = False
    
    if sum(defender_survivors.values()) == 0:
        # Wall damage (Rams)
        siege_survivors = attacker_survivors.get("quebramuros", 0) + attacker_survivors.get("ram", 0)
        if siege_survivors > 0:
            wall = next((b for b in defender_city.buildings if b.name == WALL_NAME), None)
            if wall and wall.level > 0:
                damage = max(1, int(siege_survivors ** 0.5))
                old_level = wall.level
                wall.level = max(0, wall.level - damage)
                wall_damage = (old_level, wall.level)
        
        # Catapult damage (Target Building)
        catapult_survivors = attacker_survivors.get("catapult", 0)
        if catapult_survivors > 0 and target_building:
            # If target is wall, we add to the damage (or damage it again if rams already hit it)
            # If target is something else, we find it and damage it
            
            target_b = next((b for b in defender_city.buildings if b.name == target_building), None)
            
            # Special case: if target is wall and we already damaged it with rams, we use the current (reduced) level
            if target_b and target_b.level > 0:
                # Damage formula for catapults
                catapult_damage = max(1, int(catapult_survivors ** 0.5))
                
                old_b_level = target_b.level
                target_b.level = max(0, target_b.level - catapult_damage)
                
                # If it was the wall, update wall_damage tuple to reflect total change
                if target_building == WALL_NAME and wall_damage:
                    # wall_damage is (original_level, level_after_rams)
                    # We want (original_level, level_after_catapults)
                    wall_damage = (wall_damage[0], target_b.level)
                elif target_building == WALL_NAME:
                    wall_damage = (old_b_level, target_b.level)
                else:
                    building_damage = {
                        "building": target_building,
                        "old_level": old_b_level,
                        "new_level": target_b.level
                    }

        # Loyalty reduction (Nobles)
        nobles = attacker_survivors.get("noble", 0)
        # Only allow conquest if defender is barbarian (owner_id is None)
        if nobles > 0 and defender_city.owner_id is None:
            # Each noble reduces loyalty by 20-35
            reduction = 0
            for _ in range(nobles):
                reduction += random.randint(20, 35)
            
            old_loyalty = defender_city.loyalty
            defender_city.loyalty -= reduction
            loyalty_change = reduction
            
            if defender_city.loyalty <= 0:
                conquest = True
                defender_city.owner_id = attacker_city.owner_id
                defender_city.loyalty = 25.0 # Reset loyalty for new owner
                # Troops in the city (if any survivors, which is 0 here) belong to old owner? 
                # But they are dead.
                # What about support troops? They should be sent back?
                # For simplicity, we assume all defenders are dead.

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


def build_battle_report_content(attacker_city: models.City, defender_city: models.City, battle_result: Dict) -> str:
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

    # Calculate initial troops
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
            "xp_gained": xp_gained
        },
        "defender": {
            "id": defender_city.id,
            "name": defender_city.name,
            "owner": defender_city.owner.username if defender_city.owner else "Bárbaros",
            "initial": defender_initial,
            "losses": defender_losses
        },
        "loot": loot,
        "wall_damage": wall_damage,
        "building_damage": building_damage,
        "loyalty_change": loyalty_change,
        "conquest": conquest,
        "moral": battle_result.get("moral"),
        "luck": battle_result.get("luck"),
        "effective_attack": battle_result.get("effective_attack"),
        "defense_value": battle_result.get("defense_value")
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
    
    attack_distribution, base_attack = _split_attack_by_type(attacking_troops, attacker_hero)
    defenses = _defense_values(defender_troops, None) # No hero in oasis
    wall_multiplier = 1.0 # No wall in oasis

    moral = 1.0 # No moral penalty against nature
    luck_factor = _luck()

    effective_attack = base_attack * moral * (1 + luck_factor)
    defense_value = _weighted_defense(defenses, attack_distribution, wall_multiplier)

    attacker_loss_ratio, defender_loss_ratio = _loss_ratios(effective_attack, defense_value)
    attacker_losses = _apply_losses(attacking_troops, attacker_loss_ratio)
    defender_losses = _apply_losses(defender_troops, defender_loss_ratio)

    # Hero damage logic
    if attacker_hero and attacker_loss_ratio > 0.9:
        attacker_hero.health = 0
        attacker_hero.status = "dead"
    elif attacker_hero:
        attacker_hero.health = max(0, attacker_hero.health - (attacker_loss_ratio * 100))
        if attacker_hero.health <= 0:
            attacker_hero.status = "dead"

    # Ranking points
    attacker_points_gained = sum(defender_losses.values()) # Simplified
    
    xp_gained = 0
    if attacker_city.owner:
        xp_gained = attacker_points_gained # 1 XP per unit killed

    attacker_survivors = {
        u: q - attacker_losses.get(u, 0) for u, q in attacking_troops.items()
    }
    defender_survivors = {
        u: q - defender_losses.get(u, 0) for u, q in defender_troops.items()
    }

    return {
        "attacker_losses": attacker_losses,
        "defender_losses": defender_losses,
        "attacker_survivors": attacker_survivors,
        "defender_survivors": defender_survivors,
        "xp_gained": xp_gained,
        "loot": {}, 
        "conquered": sum(defender_survivors.values()) == 0 and attacker_hero and attacker_hero.health > 0
    }


def build_oasis_report_content(attacker_city: models.City, oasis: models.Oasis, battle_result: Dict) -> str:
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
            "xp_gained": xp_gained
        },
        "defender": {
            "id": oasis.id,
            "name": f"Oasis ({oasis.resource_type})",
            "owner": "Naturaleza",
            "initial": defender_initial,
            "losses": defender_losses
        },
        "conquest": conquest,
        "loot": {},
        "moral": 1.0,
        "luck": 0.0,
    }
    
    return json.dumps(report_data)


