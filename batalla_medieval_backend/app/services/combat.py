"""Compatibility entrypoint for the deterministic combat engine.

The implementation lives in :mod:`combat_rounds`; this module keeps the
historic import path stable for movement, conquest, tests and external callers.
BM-0067 also attaches the versioned PvE oasis reward while remaining inside the
same worker transaction as the battle, so retries cannot pay twice.

BM-0068 adapts the legacy combat helper hooks to the versioned percentage-based
hero rules. This keeps the BM-0064 deterministic round engine intact while
removing its old absolute ``100 + points * 10`` hero power model. Equipped
items and allocated attributes now affect the live army through bounded bonuses
owned exclusively by :mod:`hero_rules`.
"""

import json

from . import combat_rounds as _impl
from . import hero_rules

COMBAT_ALGORITHM_VERSION = _impl.COMBAT_ALGORITHM_VERSION
COMBAT_MAX_ROUNDS = _impl.COMBAT_MAX_ROUNDS
COMBAT_ROUND_CASUALTY_SCALE = _impl.COMBAT_ROUND_CASUALTY_SCALE
UNIT_STATS = _impl.UNIT_STATS
WALL_NAME = _impl.WALL_NAME
WALL_BONUS_PER_LEVEL = _impl.WALL_BONUS_PER_LEVEL

# Capture the BM-0064 unit-only helpers before installing the BM-0068 adapters.
# The adapters are module-static (not per-request monkeypatches), so concurrent
# battles all execute the same deterministic code path.
_base_split_attack_by_type = _impl._split_attack_by_type
_base_defense_values = _impl._defense_values


def _split_attack_by_type(troops, hero=None):
    """Return army attack with category-scoped, bounded BM-0068 bonuses."""

    attack_by_type, total_attack = _base_split_attack_by_type(troops, None)
    if hero is None or getattr(hero, "status", None) != "moving" or float(getattr(hero, "health", 0.0)) <= 0:
        return attack_by_type, total_attack

    boosted = {
        category: value * (1.0 + hero_rules.attack_bonus_for_category(hero, category))
        for category, value in attack_by_type.items()
    }
    return boosted, sum(boosted.values())


def _defense_values(defender_troops, hero=None):
    """Return defenses with category-scoped, bounded BM-0068 bonuses."""

    defenses = _base_defense_values(defender_troops, None)
    if hero is None or getattr(hero, "status", None) != "home" or float(getattr(hero, "health", 0.0)) <= 0:
        return defenses

    return {
        category: value * (1.0 + hero_rules.defense_bonus_for_category(hero, category))
        for category, value in defenses.items()
    }


def _normalize_hero_xp(hero) -> None:
    """Advance every level already earned by a live in-memory hero."""

    if hero is None:
        return
    while (
        int(getattr(hero, "level", 1)) < hero_rules.HERO_MAX_LEVEL
        and int(getattr(hero, "xp", 0)) >= hero_rules.HERO_XP_TABLE[int(hero.level)]
    ):
        hero.xp -= hero_rules.HERO_XP_TABLE[int(hero.level)]
        hero.level += 1


# ``combat_rounds._resolve_rounds`` resolves these names at runtime inside its
# own module. Install the adapters once so direct and compatibility callers use
# the same authoritative BM-0068 behavior.
_impl._split_attack_by_type = _split_attack_by_type
_impl._defense_values = _defense_values

# Compatibility helpers retained for callers that imported the previous module
# internals. Authoritative resolution lives entirely in combat_rounds.
_wall_names = _impl._wall_names
_wall_bonus = _impl._wall_bonus
_moral = _impl._moral
_luck = _impl._luck
_weighted_defense = _impl._weighted_defense
_loss_ratios = _impl._loss_ratios
_apply_losses = _impl._apply_losses
_find_target_building = _impl._find_target_building


def build_battle_report_content(attacker_city, defender_city, battle_result):
    """Serialize BM-0064 combat plus the exact BM-0068 hero modifiers used."""

    report = json.loads(
        _impl.build_battle_report_content(attacker_city, defender_city, battle_result)
    )
    report["hero_rules_version"] = battle_result.get("hero_rules_version")
    report["attacker_hero_bonus"] = float(
        battle_result.get("attacker_hero_bonus", 0.0) or 0.0
    )
    report["defender_hero_bonus"] = float(
        battle_result.get("defender_hero_bonus", 0.0) or 0.0
    )
    report["attacker_hero_bonuses"] = battle_result.get("attacker_hero_bonuses", {})
    report["defender_hero_bonuses"] = battle_result.get("defender_hero_bonuses", {})
    return json.dumps(report, sort_keys=True)


def resolve_battle(*args, **kwargs):
    """Call BM-0064 with the defender hero selected by BM-0068 world scope.

    ``combat_rounds`` predates multi-world heroes and still reads the legacy
    ``owner.hero`` compatibility attribute. BM-0068 callers pass the exact
    defender hero for the movement world; expose it only for the duration of
    this pure in-memory resolution and remove the override immediately after.
    No database field or active-world preference is mutated.
    """

    defender_hero = kwargs.pop("defender_hero", None)
    defender_city = args[1] if len(args) > 1 else kwargs.get("defender_city")
    defender_owner = getattr(defender_city, "owner", None)
    had_override = False
    previous_override = None
    if defender_owner is not None and defender_hero is not None:
        had_override = hasattr(defender_owner, "_bm0068_scoped_hero")
        previous_override = getattr(defender_owner, "_bm0068_scoped_hero", None)
        defender_owner._bm0068_scoped_hero = defender_hero
    try:
        result = _impl.resolve_battle(*args, **kwargs)
        # BM-0064 credits defender XP directly on the hero object. BM-0068 owns
        # the level table, so normalize the accumulated XP before the caller's
        # surrounding worker transaction persists the battle.
        _normalize_hero_xp(defender_hero)
        result["hero_rules_version"] = hero_rules.HERO_RULES_VERSION
        attacker_hero = kwargs.get("attacker_hero")
        if attacker_hero is not None:
            result["attacker_hero_bonus"] = hero_rules.attack_bonus(attacker_hero)
            result["attacker_hero_bonuses"] = hero_rules.attack_bonuses(attacker_hero)
        if defender_hero is not None:
            result["defender_hero_bonus"] = hero_rules.defense_bonus(defender_hero)
            result["defender_hero_bonuses"] = hero_rules.defense_bonuses(defender_hero)
        return result
    finally:
        if defender_owner is not None and defender_hero is not None:
            if had_override:
                defender_owner._bm0068_scoped_hero = previous_override
            elif hasattr(defender_owner, "_bm0068_scoped_hero"):
                delattr(defender_owner, "_bm0068_scoped_hero")


def _credit_oasis_reward(attacker_city, oasis, result, *, was_wild: bool):
    """Credit the BM-0067 reward only for a first conquest of a wild oasis."""

    from . import production, pve

    tier = pve.oasis_tier(oasis)
    theoretical = pve.oasis_conquest_reward(oasis)
    credited = {}
    conquered = bool(result.get("conquered") or result.get("conquest"))
    reward_eligible = bool(was_wild and conquered)

    if reward_eligible:
        storage_limit = float(production.get_storage_limit(attacker_city))
        for resource, amount in theoretical.items():
            current = float(getattr(attacker_city, resource))
            actual = max(min(float(amount), storage_limit - current), 0.0)
            if actual > 0:
                setattr(attacker_city, resource, current + actual)
                credited[resource] = int(actual)

    result["loot"] = credited
    result["pve"] = {
        "rules_version": pve.world_rules_version(oasis.world),
        "tier": tier,
        "conquest_reward": theoretical,
        "credited_reward": credited,
        "reward_eligible": reward_eligible,
        "was_wild": bool(was_wild),
    }
    return result


def resolve_oasis_battle(*args, **kwargs):
    """Preserve oasis scoring while applying PvE and BM-0068 hero rules."""

    attacker_city = args[0] if args else kwargs.get("attacker_city")
    oasis = args[1] if len(args) > 1 else kwargs.get("oasis")
    was_wild = bool(oasis is not None and getattr(oasis, "owner_city_id", None) is None)
    owner = getattr(attacker_city, "owner", None)
    previous_points = getattr(owner, "attacker_points", None) if owner else None
    result = _impl.resolve_oasis_battle(*args, **kwargs)
    if owner is not None and previous_points is not None:
        owner.attacker_points = previous_points
    attacker_hero = kwargs.get("attacker_hero")
    result["hero_rules_version"] = hero_rules.HERO_RULES_VERSION
    if attacker_hero is not None:
        result["attacker_hero_bonus"] = hero_rules.attack_bonus(attacker_hero)
        result["attacker_hero_bonuses"] = hero_rules.attack_bonuses(attacker_hero)
    if attacker_city is not None and oasis is not None:
        result = _credit_oasis_reward(
            attacker_city,
            oasis,
            result,
            was_wild=was_wild,
        )
    return result


def build_oasis_report_content(attacker_city, oasis, battle_result):
    """Add BM-0067 PvE and BM-0068 hero audit metadata to the oasis report."""

    report = json.loads(_impl.build_oasis_report_content(attacker_city, oasis, battle_result))
    report["loot"] = battle_result.get("loot", {})
    report["pve"] = battle_result.get("pve", {})
    report["hero_rules_version"] = battle_result.get("hero_rules_version")
    report["attacker_hero_bonus"] = float(
        battle_result.get("attacker_hero_bonus", 0.0) or 0.0
    )
    report["attacker_hero_bonuses"] = battle_result.get("attacker_hero_bonuses", {})
    return json.dumps(report, sort_keys=True)
