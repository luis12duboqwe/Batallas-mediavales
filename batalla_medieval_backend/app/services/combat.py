"""Compatibility entrypoint for the deterministic combat engine.

The implementation lives in :mod:`combat_rounds`; this module keeps the
historic import path stable for movement, conquest, tests and external callers.
BM-0067 also attaches the versioned PvE oasis reward while remaining inside the
same worker transaction as the battle, so retries cannot pay twice.
"""

import json

from . import combat_rounds as _impl

COMBAT_ALGORITHM_VERSION = _impl.COMBAT_ALGORITHM_VERSION
COMBAT_MAX_ROUNDS = _impl.COMBAT_MAX_ROUNDS
COMBAT_ROUND_CASUALTY_SCALE = _impl.COMBAT_ROUND_CASUALTY_SCALE
UNIT_STATS = _impl.UNIT_STATS
WALL_NAME = _impl.WALL_NAME
WALL_BONUS_PER_LEVEL = _impl.WALL_BONUS_PER_LEVEL

# Compatibility helpers retained for callers that imported the previous module
# internals. Authoritative resolution lives entirely in combat_rounds.
_wall_names = _impl._wall_names
_split_attack_by_type = _impl._split_attack_by_type
_defense_values = _impl._defense_values
_wall_bonus = _impl._wall_bonus
_moral = _impl._moral
_luck = _impl._luck
_weighted_defense = _impl._weighted_defense
_loss_ratios = _impl._loss_ratios
_apply_losses = _impl._apply_losses
_find_target_building = _impl._find_target_building

build_battle_report_content = _impl.build_battle_report_content


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
        return _impl.resolve_battle(*args, **kwargs)
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
    """Preserve oasis scoring while applying the BM-0067 PvE reward contract.

    BM-0064 changed combat determinism/rounds only. Oasis combat historically
    returned ``xp_gained`` for the hero but did not award player attacker
    ranking points, so keep that boundary stable. BM-0067 adds a separately
    versioned conquest reward, credited atomically with battle resolution and
    capped by the attacker's server-authoritative storage capacity.

    The reward is a one-time wild-oasis capture reward. Ownership is sampled
    before combat because the authoritative combat engine mutates
    ``owner_city_id`` when conquest succeeds; checking ownership afterwards
    would make an already-owned oasis indistinguishable from a first capture.
    """

    attacker_city = args[0] if args else kwargs.get("attacker_city")
    oasis = args[1] if len(args) > 1 else kwargs.get("oasis")
    was_wild = bool(oasis is not None and getattr(oasis, "owner_city_id", None) is None)
    owner = getattr(attacker_city, "owner", None)
    previous_points = getattr(owner, "attacker_points", None) if owner else None
    result = _impl.resolve_oasis_battle(*args, **kwargs)
    if owner is not None and previous_points is not None:
        owner.attacker_points = previous_points
    if attacker_city is not None and oasis is not None:
        result = _credit_oasis_reward(
            attacker_city,
            oasis,
            result,
            was_wild=was_wild,
        )
    return result


def build_oasis_report_content(attacker_city, oasis, battle_result):
    """Add BM-0067 PvE audit/reward metadata to the canonical oasis report."""

    report = json.loads(_impl.build_oasis_report_content(attacker_city, oasis, battle_result))
    report["loot"] = battle_result.get("loot", {})
    report["pve"] = battle_result.get("pve", {})
    return json.dumps(report, sort_keys=True)
