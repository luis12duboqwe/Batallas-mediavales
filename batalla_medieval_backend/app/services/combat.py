import math
import random
from typing import Dict, Tuple

from .. import models
from . import event as event_service

UNIT_STATS: Dict[str, Dict[str, float]] = {
    "lancero_comun": {"attack": 10, "def_inf": 20, "def_cav": 10, "def_siege": 20, "type": "infantry"},
    "soldado_de_acero": {"attack": 25, "def_inf": 40, "def_cav": 30, "def_siege": 40, "type": "infantry"},
    "arquero_real": {"attack": 30, "def_inf": 10, "def_cav": 40, "def_siege": 15, "type": "infantry"},
    "jinete_explorador": {"attack": 60, "def_inf": 20, "def_cav": 20, "def_siege": 20, "type": "cavalry"},
    "caballero_imperial": {"attack": 100, "def_inf": 40, "def_cav": 60, "def_siege": 40, "type": "cavalry"},
    "infiltrador": {"attack": 0, "def_inf": 0, "def_cav": 0, "def_siege": 0, "type": "infantry"},
    "quebramuros": {"attack": 2, "def_inf": 50, "def_cav": 50, "def_siege": 80, "type": "siege"},
    "tormenta_de_piedra": {"attack": 2, "def_inf": 100, "def_cav": 100, "def_siege": 120, "type": "siege"},
    # Aliases for backwards compatibility with previous unit naming
    "basic_infantry": {"attack": 10, "def_inf": 20, "def_cav": 10, "def_siege": 20, "type": "infantry"},
    "heavy_infantry": {"attack": 25, "def_inf": 40, "def_cav": 30, "def_siege": 40, "type": "infantry"},
    "archer": {"attack": 30, "def_inf": 10, "def_cav": 40, "def_siege": 15, "type": "infantry"},
    "fast_cavalry": {"attack": 60, "def_inf": 20, "def_cav": 20, "def_siege": 20, "type": "cavalry"},
    "heavy_cavalry": {"attack": 100, "def_inf": 40, "def_cav": 60, "def_siege": 40, "type": "cavalry"},
    "spy": {"attack": 0, "def_inf": 0, "def_cav": 0, "def_siege": 0, "type": "infantry"},
    "ram": {"attack": 2, "def_inf": 50, "def_cav": 50, "def_siege": 80, "type": "siege"},
    "catapult": {"attack": 2, "def_inf": 100, "def_cav": 100, "def_siege": 120, "type": "siege"},
}

WALL_NAME = "Muralla de Guardia"
WALL_BONUS_PER_LEVEL = 0.05


def _split_attack_by_type(troops: Dict[str, int]) -> Tuple[Dict[str, float], float]:
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
    return attack_by_type, total_attack


def _defense_values(defender_troops: Dict[str, int]) -> Dict[str, float]:
    defenses = {"infantry": 0.0, "cavalry": 0.0, "siege": 0.0}
    for unit, amount in defender_troops.items():
        stats = UNIT_STATS.get(unit)
        if not stats:
            continue
        defenses["infantry"] += stats.get("def_inf", 0) * amount
        defenses["cavalry"] += stats.get("def_cav", 0) * amount
        defenses["siege"] += stats.get("def_siege", stats.get("def_inf", 0)) * amount
    return defenses


def _wall_bonus(city: models.City) -> float:
    wall = next((b for b in city.buildings if b.name == WALL_NAME), None)
    if not wall:
        return 1.0
    return 1.0 + wall.level * WALL_BONUS_PER_LEVEL


def _moral(attacker_strength: float, defender_strength: float) -> float:
    attacker_points = max(attacker_strength, 1)
    defender_points = max(defender_strength, 1)
    return min(1.5, max(0.3, math.sqrt(defender_points / attacker_points)))


def _luck() -> float:
    return random.uniform(-0.25, 0.25)


def _weighted_defense(defenses: Dict[str, float], attack_distribution: Dict[str, float], wall_multiplier: float) -> float:
    total_attack = sum(attack_distribution.values()) or 1
    ratios = {k: v / total_attack for k, v in attack_distribution.items()}
    defense_value = (
        defenses["infantry"] * ratios.get("infantry", 0)
        + defenses["cavalry"] * ratios.get("cavalry", 0)
        + defenses["siege"] * ratios.get("siege", 0)
    )
    return defense_value * wall_multiplier


def _loss_ratios(effective_attack: float, defense_value: float) -> Tuple[float, float]:
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
    losses = {}
    for unit, amount in troops.items():
        losses[unit] = min(amount, int(round(amount * loss_ratio)))
    return losses


def resolve_battle(
    attacker_city: models.City,
    defender_city: models.City,
    attacking_troops: Dict[str, int],
    modifiers: Dict[str, float] | None = None,
):
    modifiers = modifiers or event_service.DEFAULT_MODIFIERS
    defender_troops = {troop.unit_type: troop.quantity for troop in defender_city.troops}

    attack_distribution, base_attack = _split_attack_by_type(attacking_troops)
    defenses = _defense_values(defender_troops)
    wall_multiplier = _wall_bonus(defender_city)

    moral = _moral(base_attack, sum(defenses.values()))
    luck_factor = _luck()

    effective_attack = base_attack * moral * (1 + luck_factor)
    defense_value = _weighted_defense(defenses, attack_distribution, wall_multiplier)

    attacker_loss_ratio, defender_loss_ratio = _loss_ratios(effective_attack, defense_value)
    attacker_losses = _apply_losses(attacking_troops, attacker_loss_ratio)
    defender_losses = _apply_losses(defender_troops, defender_loss_ratio)

    attacker_survivors = {u: max(0, attacking_troops.get(u, 0) - attacker_losses.get(u, 0)) for u in attacking_troops}
    defender_survivors = {u: max(0, defender_troops.get(u, 0) - defender_losses.get(u, 0)) for u in defender_troops}

    loot = {"wood": 0, "clay": 0, "iron": 0}
    if sum(defender_survivors.values()) == 0 and base_attack > 0:
        loot_multiplier = modifiers.get("loot_modifier", 1.0)
        loot = {
            "wood": int(defender_city.wood * 0.3 * loot_multiplier),
            "clay": int(defender_city.clay * 0.3 * loot_multiplier),
            "iron": int(defender_city.iron * 0.3 * loot_multiplier),
        }
        defender_city.wood -= loot["wood"]
        defender_city.clay -= loot["clay"]
        defender_city.iron -= loot["iron"]
        attacker_city.wood += loot["wood"]
        attacker_city.clay += loot["clay"]
        attacker_city.iron += loot["iron"]

    wall_damage = None
    siege_survivors = attacker_survivors.get("quebramuros", 0) + attacker_survivors.get("tormenta_de_piedra", 0)
    if siege_survivors > 0 and sum(defender_survivors.values()) == 0:
        wall = next((b for b in defender_city.buildings if b.name == WALL_NAME), None)
        if wall and wall.level > 0:
            damage = max(1, int(siege_survivors ** 0.5))
            old_level = wall.level
            wall.level = max(0, wall.level - damage)
            wall_damage = (old_level, wall.level)

    report = {
        "attacker_losses": attacker_losses,
        "defender_losses": defender_losses,
        "attacker_survivors": attacker_survivors,
        "defender_survivors": defender_survivors,
        "loot": loot,
        "wall_damage": wall_damage,
        "moral": moral,
        "luck": luck_factor,
        "effective_attack": effective_attack,
        "defense_value": defense_value,
    }
    return report


def build_battle_report_html(attacker_city: models.City, defender_city: models.City, battle_result: Dict) -> str:
    attacker_losses = battle_result.get("attacker_losses", {})
    defender_losses = battle_result.get("defender_losses", {})
    attacker_survivors = battle_result.get("attacker_survivors", {})
    defender_survivors = battle_result.get("defender_survivors", {})
    loot = battle_result.get("loot", {})
    wall_damage = battle_result.get("wall_damage")

    def _format_troops(troops: Dict[str, int]):
        return "".join(f"<li>{unit}: {amount}</li>" for unit, amount in troops.items()) or "<li>Ninguna tropa</li>"

    wall_section = ""
    if wall_damage:
        wall_section = f"<p>Muralla dañada: Nivel {wall_damage[0]} → Nivel {wall_damage[1]}</p>"

    html = f"""
    <h2>Informe de batalla</h2>
    <p><strong>Atacante:</strong> {attacker_city.name} (Jugador {attacker_city.owner.username})</p>
    <p><strong>Defensor:</strong> {defender_city.name} (Jugador {defender_city.owner.username})</p>
    <h3>Tropas desplegadas</h3>
    <p>Atacante:</p><ul>{_format_troops(attacker_survivors)}</ul>
    <p>Defensor:</p><ul>{_format_troops(defender_survivors)}</ul>
    <h3>Bajas</h3>
    <p>Atacante:</p><ul>{_format_troops(attacker_losses)}</ul>
    <p>Defensor:</p><ul>{_format_troops(defender_losses)}</ul>
    <h3>Botín</h3>
    <p>Madera: {loot.get('wood', 0)} | Barro: {loot.get('clay', 0)} | Hierro: {loot.get('iron', 0)}</p>
    {wall_section}
    <p>Moral aplicada: {battle_result.get('moral'):.2f} | Suerte: {battle_result.get('luck'):.2f}</p>
    <p>Ataque efectivo: {battle_result.get('effective_attack'):.2f} | Defensa efectiva: {battle_result.get('defense_value'):.2f}</p>
    """
    return html
