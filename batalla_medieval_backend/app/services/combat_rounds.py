"""Deterministic instant round combat for BM-0064.

The resolver is server-authoritative, has no terrain/obstacle layer and consumes
only the canonical unit statistics from :mod:`balance`. Every battle owns an
explicit audit seed. Given the same initial state and seed, round luck, losses,
barbarian loyalty damage and the final result are reproducible.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any, Dict, Mapping, Tuple

from .. import models
from . import balance
from . import event as event_service

COMBAT_ALGORITHM_VERSION = "2026.08.24-bm0064-rounds-v1"
COMBAT_MAX_ROUNDS = 8
COMBAT_ROUND_CASUALTY_SCALE = 0.35

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
    for unit, raw_amount in troops.items():
        amount = max(int(raw_amount), 0)
        stats = UNIT_STATS.get(unit)
        if not stats or amount <= 0:
            continue
        attack_value = float(stats.get("attack", 0)) * amount
        attack_by_type[stats["type"]] += attack_value
        total_attack += attack_value

    if hero and hero.status == "moving" and hero.health > 0:
        hero_attack = 100 + (hero.attack_points * 10)
        attack_by_type["infantry"] += hero_attack
        total_attack += hero_attack

    return attack_by_type, total_attack


def _defense_values(
    defender_troops: Dict[str, int], hero: models.Hero | None = None
) -> Dict[str, float]:
    """Calculate defense values per troop category."""

    defenses = {"infantry": 0.0, "cavalry": 0.0, "siege": 0.0}
    for unit, raw_amount in defender_troops.items():
        amount = max(int(raw_amount), 0)
        stats = UNIT_STATS.get(unit)
        if not stats or amount <= 0:
            continue
        defenses["infantry"] += float(stats.get("def_inf", 0)) * amount
        defenses["cavalry"] += float(stats.get("def_cav", 0)) * amount
        defenses["siege"] += float(stats.get("def_siege", stats.get("def_inf", 0))) * amount

    if hero and hero.status == "home" and hero.health > 0:
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
    return 1.0 + max(int(wall.level), 0) * WALL_BONUS_PER_LEVEL


def _wall_level(city: models.City) -> int:
    wall = next((b for b in city.buildings if b.name in _wall_names()), None)
    return max(int(wall.level), 0) if wall else 0


def _moral(attacker_strength: float, defender_strength: float) -> float:
    """Calculate morale based on current attacker and defender strengths."""

    attacker_points = max(float(attacker_strength), 1.0)
    defender_points = max(float(defender_strength), 1.0)
    raw = math.sqrt(defender_points / attacker_points)
    return min(balance.MORALE_MAX, max(balance.MORALE_MIN, raw))


def _luck(rng: random.Random | None = None) -> float:
    """Return luck inside the versioned limits.

    Live combat always supplies a deterministic RNG. The optional fallback keeps
    this helper useful for isolated compatibility callers without making the
    global ``random`` module part of authoritative combat.
    """

    rng = rng or random.Random()
    return rng.uniform(balance.LUCK_MIN, balance.LUCK_MAX)


def _weighted_defense(
    defenses: Dict[str, float],
    attack_distribution: Dict[str, float],
    wall_multiplier: float,
) -> float:
    """Weight defense by attack distribution and wall effects."""

    total_attack = sum(attack_distribution.values()) or 1.0
    ratios = {key: value / total_attack for key, value in attack_distribution.items()}
    defense_value = (
        defenses["infantry"] * ratios.get("infantry", 0.0)
        + defenses["cavalry"] * ratios.get("cavalry", 0.0)
        + defenses["siege"] * ratios.get("siege", 0.0)
    )
    return defense_value * wall_multiplier


def _loss_ratios(effective_attack: float, defense_value: float) -> Tuple[float, float]:
    """Determine attacker and defender pressure from current strengths."""

    if effective_attack <= 0:
        return 1.0, 0.0
    if defense_value <= 0:
        return 0.0, 1.0

    decisive = balance.DECISIVE_STRENGTH_RATIO
    if effective_attack > defense_value * decisive:
        return max(0.05, (defense_value / effective_attack) ** 0.5), 1.0
    if defense_value > effective_attack * decisive:
        return 1.0, max(0.05, (effective_attack / defense_value) ** 0.5)

    balance_factor = effective_attack / defense_value
    attacker_ratio = min(1.0, (1 / balance_factor) ** 0.5)
    defender_ratio = min(1.0, balance_factor**0.5)
    return attacker_ratio, defender_ratio


def _apply_losses(troops: Dict[str, int], loss_ratio: float) -> Dict[str, int]:
    """Compatibility aggregate loss helper used by older callers/tests."""

    ratio = min(max(float(loss_ratio), 0.0), 1.0)
    return {
        unit: min(max(int(amount), 0), int(round(max(int(amount), 0) * ratio)))
        for unit, amount in troops.items()
    }


def _apply_round_losses(
    troops: Mapping[str, int],
    pressure_ratio: float,
    rng: random.Random,
) -> Dict[str, int]:
    """Apply one bounded round of casualties with deterministic fractional rounding."""

    pressure = min(max(float(pressure_ratio), 0.0), 1.0)
    ratio = min(1.0, pressure * COMBAT_ROUND_CASUALTY_SCALE)
    losses: Dict[str, int] = {}
    for unit in sorted(troops):
        amount = max(int(troops[unit]), 0)
        if amount <= 0 or ratio <= 0:
            losses[unit] = 0
            continue
        expected = amount * ratio
        whole = int(math.floor(expected))
        fractional = expected - whole
        loss = whole + (1 if fractional > 0 and rng.random() < fractional else 0)
        losses[unit] = min(amount, loss)
    return losses


def _subtract_losses(
    troops: Mapping[str, int], losses: Mapping[str, int]
) -> Dict[str, int]:
    return {
        unit: max(0, int(amount) - int(losses.get(unit, 0)))
        for unit, amount in troops.items()
    }


def _total_losses(
    initial: Mapping[str, int], survivors: Mapping[str, int]
) -> Dict[str, int]:
    return {
        unit: max(0, int(amount) - int(survivors.get(unit, 0)))
        for unit, amount in initial.items()
    }


def _canonical_unit_name(unit: str) -> str:
    return balance.LEGACY_UNIT_ALIASES.get(unit, unit)


def _population_weight(unit: str) -> int:
    catalog = balance.UNIT_CATALOG.get(_canonical_unit_name(unit), {})
    return max(int(catalog.get("population", 1)), 1)


def _army_population(troops: Mapping[str, int]) -> int:
    return sum(
        max(int(amount), 0) * _population_weight(unit)
        for unit, amount in troops.items()
    )


def _loss_fraction(
    initial: Mapping[str, int], survivors: Mapping[str, int]
) -> float:
    initial_population = _army_population(initial)
    if initial_population <= 0:
        return 0.0
    survivor_population = _army_population(survivors)
    return min(1.0, max(0.0, 1.0 - (survivor_population / initial_population)))


def _apply_hero_losses(hero: models.Hero | None, loss_fraction: float) -> None:
    if not hero or hero.health <= 0:
        return
    if loss_fraction > 0.90:
        hero.health = 0
        hero.status = "dead"
        return
    hero.health = max(0, hero.health - (loss_fraction * 100))
    if hero.health <= 0:
        hero.status = "dead"


def _stable_troop_payload(troops: Mapping[str, int]) -> Dict[str, int]:
    return {
        unit: max(int(amount), 0)
        for unit, amount in sorted(troops.items())
        if int(amount) > 0
    }


def _derive_seed(
    *,
    battle_kind: str,
    attacker_city_id: int | None,
    defender_id: int | None,
    attacking_troops: Mapping[str, int],
    defender_troops: Mapping[str, int],
    wall_level: int = 0,
    target_building: str | None = None,
    attacker_progress: int = 0,
    defender_progress: int = 0,
) -> str:
    """Derive a retry-stable seed from immutable/current pre-battle state."""

    payload = {
        "algorithm": COMBAT_ALGORITHM_VERSION,
        "balance": balance.BALANCE_VERSION,
        "kind": battle_kind,
        "attacker_city_id": attacker_city_id,
        "defender_id": defender_id,
        "attacking_troops": _stable_troop_payload(attacking_troops),
        "defender_troops": _stable_troop_payload(defender_troops),
        "wall_level": max(int(wall_level), 0),
        "target_building": target_building or "",
        # Progress points change after a committed battle, so a later identical
        # attack does not silently reuse the same random stream. A rollback
        # restores them, keeping retries reproducible.
        "attacker_progress": max(int(attacker_progress), 0),
        "defender_progress": max(int(defender_progress), 0),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _seeded_rng(seed: str | int) -> random.Random:
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    return random.Random(int(digest, 16))


def _resolve_rounds(
    *,
    attacking_troops: Mapping[str, int],
    defender_troops: Mapping[str, int],
    wall_multiplier: float,
    rng: random.Random,
    attacker_hero: models.Hero | None = None,
    defender_hero: models.Hero | None = None,
    moral_override: float | None = None,
) -> Dict[str, Any]:
    """Resolve an instant battle as a bounded sequence of server-side rounds."""

    attacker_initial = _stable_troop_payload(attacking_troops)
    defender_initial = _stable_troop_payload(defender_troops)
    attacker_survivors = dict(attacker_initial)
    defender_survivors = dict(defender_initial)
    rounds: list[Dict[str, Any]] = []

    for round_number in range(1, COMBAT_MAX_ROUNDS + 1):
        if not any(attacker_survivors.values()) or not any(defender_survivors.values()):
            break

        attack_distribution, base_attack = _split_attack_by_type(
            attacker_survivors, attacker_hero
        )
        defenses = _defense_values(defender_survivors, defender_hero)
        defense_value = _weighted_defense(
            defenses, attack_distribution, wall_multiplier
        )
        moral = (
            float(moral_override)
            if moral_override is not None
            else _moral(base_attack, defense_value)
        )
        luck_factor = _luck(rng)
        effective_attack = base_attack * moral * (1 + luck_factor)

        if effective_attack <= 0 and defense_value <= 0:
            attacker_round_losses = {}
            defender_round_losses = {}
        elif effective_attack <= 0:
            attacker_round_losses = dict(attacker_survivors)
            defender_round_losses = {
                unit: 0 for unit in defender_survivors
            }
        elif defense_value <= 0:
            attacker_round_losses = {
                unit: 0 for unit in attacker_survivors
            }
            defender_round_losses = dict(defender_survivors)
        else:
            attacker_pressure, defender_pressure = _loss_ratios(
                effective_attack, defense_value
            )
            attacker_round_losses = _apply_round_losses(
                attacker_survivors, attacker_pressure, rng
            )
            defender_round_losses = _apply_round_losses(
                defender_survivors, defender_pressure, rng
            )

        attacker_before = dict(attacker_survivors)
        defender_before = dict(defender_survivors)
        attacker_survivors = _subtract_losses(
            attacker_survivors, attacker_round_losses
        )
        defender_survivors = _subtract_losses(
            defender_survivors, defender_round_losses
        )

        rounds.append(
            {
                "round": round_number,
                "attacker_before": attacker_before,
                "defender_before": defender_before,
                "attacker_losses": attacker_round_losses,
                "defender_losses": defender_round_losses,
                "attacker_after": dict(attacker_survivors),
                "defender_after": dict(defender_survivors),
                "moral": moral,
                "luck": luck_factor,
                "base_attack": base_attack,
                "effective_attack": effective_attack,
                "defense_value": defense_value,
                "wall_multiplier": wall_multiplier,
            }
        )

    attacker_alive = any(attacker_survivors.values())
    defender_alive = any(defender_survivors.values())
    if attacker_alive and not defender_alive:
        outcome = "attacker_victory"
    elif defender_alive and not attacker_alive:
        outcome = "defender_victory"
    elif not attacker_alive and not defender_alive:
        outcome = "mutual_destruction"
    else:
        outcome = "stalemate"

    last = rounds[-1] if rounds else {}
    morals = [float(item["moral"]) for item in rounds]
    luck_values = [float(item["luck"]) for item in rounds]
    return {
        "attacker_initial": attacker_initial,
        "defender_initial": defender_initial,
        "attacker_survivors": attacker_survivors,
        "defender_survivors": defender_survivors,
        "attacker_losses": _total_losses(attacker_initial, attacker_survivors),
        "defender_losses": _total_losses(defender_initial, defender_survivors),
        "rounds": rounds,
        "round_count": len(rounds),
        "outcome": outcome,
        # Compatibility summary fields for current API/UI.
        "moral": (sum(morals) / len(morals)) if morals else 1.0,
        "luck": (sum(luck_values) / len(luck_values)) if luck_values else 0.0,
        "effective_attack": float(last.get("effective_attack", 0.0)),
        "defense_value": float(last.get("defense_value", 0.0)),
    }


def _find_target_building(city: models.City, target_building: str):
    names = {target_building}
    if target_building in _wall_names():
        names = _wall_names()
    return next((building for building in city.buildings if building.name in names), None)


def _combat_metadata(result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "algorithm_version": result.get(
            "combat_version", COMBAT_ALGORITHM_VERSION
        ),
        "balance_version": result.get("balance_version", balance.BALANCE_VERSION),
        "seed": result.get("seed"),
        "round_count": int(result.get("round_count", 0) or 0),
        "outcome": result.get("outcome"),
        "rounds": result.get("rounds", []),
    }


def resolve_battle(
    attacker_city: models.City,
    defender_city: models.City,
    attacking_troops: Dict[str, int],
    modifiers: Dict[str, float] | None = None,
    attacker_hero: models.Hero | None = None,
    target_building: str | None = None,
    seed: str | int | None = None,
):
    """Resolve deterministic instant round combat between two cities."""

    modifiers = modifiers or event_service.DEFAULT_MODIFIERS
    defender_troops = {
        troop.unit_type: troop.quantity for troop in defender_city.troops
    }
    defender_hero = defender_city.owner.hero if defender_city.owner else None
    if defender_hero and defender_hero.city_id != defender_city.id:
        defender_hero = None

    attacker_progress = (
        int(attacker_city.owner.attacker_points)
        if attacker_city.owner
        else 0
    )
    defender_progress = (
        int(defender_city.owner.defender_points)
        if defender_city.owner
        else 0
    )
    audit_seed = str(
        seed
        if seed is not None
        else _derive_seed(
            battle_kind="city",
            attacker_city_id=attacker_city.id,
            defender_id=defender_city.id,
            attacking_troops=attacking_troops,
            defender_troops=defender_troops,
            wall_level=_wall_level(defender_city),
            target_building=target_building,
            attacker_progress=attacker_progress,
            defender_progress=defender_progress,
        )
    )
    rng = _seeded_rng(audit_seed)

    round_result = _resolve_rounds(
        attacking_troops=attacking_troops,
        defender_troops=defender_troops,
        wall_multiplier=_wall_bonus(defender_city),
        rng=rng,
        attacker_hero=attacker_hero,
        defender_hero=defender_hero,
    )
    attacker_losses = round_result["attacker_losses"]
    defender_losses = round_result["defender_losses"]
    attacker_survivors = round_result["attacker_survivors"]
    defender_survivors = round_result["defender_survivors"]

    _apply_hero_losses(
        attacker_hero, _loss_fraction(attacking_troops, attacker_survivors)
    )
    _apply_hero_losses(
        defender_hero, _loss_fraction(defender_troops, defender_survivors)
    )

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

    # Loot belongs only to a successful surviving attacking army. Movement
    # service carries it on the return march instead of crediting it at impact.
    loot = {resource: 0 for resource in balance.RESOURCE_FIELDS}
    if (
        round_result["outcome"] == "attacker_victory"
        and any(attacker_survivors.values())
    ):
        total_carry = 0
        for unit, amount in attacker_survivors.items():
            stats = UNIT_STATS.get(unit)
            if stats:
                total_carry += int(stats.get("carry", 0)) * int(amount)

        loot_modifier = max(float(modifiers.get("loot_modifier", 1.0)), 0.0)
        effective_carry = total_carry * loot_modifier
        available = {
            resource: max(float(getattr(defender_city, resource)), 0.0)
            for resource in balance.RESOURCE_FIELDS
        }
        total_resources = sum(available.values())
        if total_resources > 0 and effective_carry > 0:
            take_ratio = min(1.0, effective_carry / total_resources)
            loot = {
                resource: int(amount * take_ratio)
                for resource, amount in available.items()
            }
            for resource, amount in loot.items():
                setattr(
                    defender_city,
                    resource,
                    getattr(defender_city, resource) - amount,
                )
                setattr(
                    attacker_city,
                    resource,
                    getattr(attacker_city, resource) + amount,
                )

    wall_damage = None
    building_damage = None
    loyalty_change = 0.0
    conquest = False

    if round_result["outcome"] == "attacker_victory":
        siege_survivors = (
            attacker_survivors.get("quebramuros", 0)
            + attacker_survivors.get("ram", 0)
        )
        if siege_survivors > 0:
            wall = next(
                (building for building in defender_city.buildings if building.name in _wall_names()),
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
                rng.randint(
                    balance.BARBARIAN_LOYALTY_DROP_MIN,
                    balance.BARBARIAN_LOYALTY_DROP_MAX,
                )
                for _ in range(nobles)
            )
            defender_city.loyalty -= reduction
            loyalty_change = float(reduction)

            if defender_city.loyalty <= 0:
                conquest = True
                defender_city.owner_id = attacker_city.owner_id
                defender_city.loyalty = balance.BARBARIAN_CONQUEST_RESET_LOYALTY

    return {
        **round_result,
        "loot": loot,
        "wall_damage": wall_damage,
        "building_damage": building_damage,
        "loyalty_change": loyalty_change,
        "conquest": conquest,
        "xp_gained": xp_gained,
        "seed": audit_seed,
        "combat_version": COMBAT_ALGORITHM_VERSION,
        "balance_version": balance.BALANCE_VERSION,
    }


def build_battle_report_content(
    attacker_city: models.City,
    defender_city: models.City,
    battle_result: Dict,
) -> str:
    """Generate an auditable JSON battle report for attacker and defender."""

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
        "combat": _combat_metadata(battle_result),
        "attacker": {
            "id": attacker_city.id,
            "name": attacker_city.name,
            "owner": attacker_city.owner.username if attacker_city.owner else "Bárbaros",
            "initial": attacker_initial,
            "losses": attacker_losses,
            "survivors": attacker_survivors,
            "xp_gained": xp_gained,
        },
        "defender": {
            "id": defender_city.id,
            "name": defender_city.name,
            "owner": defender_city.owner.username if defender_city.owner else "Bárbaros",
            "initial": defender_initial,
            "losses": defender_losses,
            "survivors": defender_survivors,
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

    return json.dumps(report_data, sort_keys=True)


def resolve_oasis_battle(
    attacker_city: models.City,
    oasis: models.Oasis,
    attacking_troops: Dict[str, int],
    modifiers: Dict[str, float] | None = None,
    attacker_hero: models.Hero | None = None,
    seed: str | int | None = None,
):
    """Resolve deterministic round combat against an oasis."""

    _ = modifiers or event_service.DEFAULT_MODIFIERS
    defender_troops = oasis.troops or {}
    attacker_progress = (
        int(attacker_city.owner.attacker_points)
        if attacker_city.owner
        else 0
    )
    audit_seed = str(
        seed
        if seed is not None
        else _derive_seed(
            battle_kind="oasis",
            attacker_city_id=attacker_city.id,
            defender_id=oasis.id,
            attacking_troops=attacking_troops,
            defender_troops=defender_troops,
            attacker_progress=attacker_progress,
        )
    )
    rng = _seeded_rng(audit_seed)

    round_result = _resolve_rounds(
        attacking_troops=attacking_troops,
        defender_troops=defender_troops,
        wall_multiplier=1.0,
        rng=rng,
        attacker_hero=attacker_hero,
        defender_hero=None,
        moral_override=1.0,
    )
    attacker_survivors = round_result["attacker_survivors"]
    defender_survivors = round_result["defender_survivors"]
    _apply_hero_losses(
        attacker_hero, _loss_fraction(attacking_troops, attacker_survivors)
    )

    attacker_points_gained = sum(round_result["defender_losses"].values())
    xp_gained = attacker_points_gained if attacker_city.owner else 0
    if attacker_city.owner:
        attacker_city.owner.attacker_points += attacker_points_gained

    conquered = bool(
        round_result["outcome"] == "attacker_victory"
        and attacker_hero
        and attacker_hero.health > 0
    )

    return {
        **round_result,
        "xp_gained": xp_gained,
        "loot": {},
        "conquered": conquered,
        "conquest": conquered,
        "seed": audit_seed,
        "combat_version": COMBAT_ALGORITHM_VERSION,
        "balance_version": balance.BALANCE_VERSION,
    }


def build_oasis_report_content(
    attacker_city: models.City,
    oasis: models.Oasis,
    battle_result: Dict,
) -> str:
    """Generate an auditable JSON report for oasis combat."""

    attacker_losses = battle_result.get("attacker_losses", {})
    defender_losses = battle_result.get("defender_losses", {})
    attacker_survivors = battle_result.get("attacker_survivors", {})
    defender_survivors = battle_result.get("defender_survivors", {})
    conquest = battle_result.get(
        "conquest", battle_result.get("conquered", False)
    )
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
        "combat": _combat_metadata(battle_result),
        "attacker": {
            "id": attacker_city.id,
            "name": attacker_city.name,
            "owner": attacker_city.owner.username if attacker_city.owner else "Bárbaros",
            "initial": attacker_initial,
            "losses": attacker_losses,
            "survivors": attacker_survivors,
            "xp_gained": xp_gained,
        },
        "defender": {
            "id": oasis.id,
            "name": f"Oasis ({oasis.resource_type})",
            "owner": "Naturaleza",
            "initial": defender_initial,
            "losses": defender_losses,
            "survivors": defender_survivors,
        },
        "conquest": conquest,
        "loot": {},
        "moral": battle_result.get("moral", 1.0),
        "luck": battle_result.get("luck", 0.0),
        "effective_attack": battle_result.get("effective_attack"),
        "defense_value": battle_result.get("defense_value"),
    }

    return json.dumps(report_data, sort_keys=True)
