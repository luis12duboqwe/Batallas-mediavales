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

resolve_battle = _impl.resolve_battle
build_battle_report_content = _impl.build_battle_report_content


def _credit_oasis_reward(attacker_city, oasis, result):
    """Credit the BM-0067 conquest reward without exceeding city storage."""

    from . import production, pve

    tier = pve.oasis_tier(oasis)
    theoretical = pve.oasis_conquest_reward(oasis)
    credited = {}

    if result.get("conquered") or result.get("conquest"):
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
    }
    return result


def resolve_oasis_battle(*args, **kwargs):
    """Preserve oasis scoring while applying the BM-0067 PvE reward contract.

    BM-0064 changed combat determinism/rounds only. Oasis combat historically
    returned ``xp_gained`` for the hero but did not award player attacker
    ranking points, so keep that boundary stable. BM-0067 adds a separately
    versioned conquest reward, credited atomically with battle resolution and
    capped by the attacker's server-authoritative storage capacity.
    """

    attacker_city = args[0] if args else kwargs.get("attacker_city")
    oasis = args[1] if len(args) > 1 else kwargs.get("oasis")
    owner = getattr(attacker_city, "owner", None)
    previous_points = getattr(owner, "attacker_points", None) if owner else None
    result = _impl.resolve_oasis_battle(*args, **kwargs)
    if owner is not None and previous_points is not None:
        owner.attacker_points = previous_points
    if attacker_city is not None and oasis is not None:
        result = _credit_oasis_reward(attacker_city, oasis, result)
    return result


def build_oasis_report_content(attacker_city, oasis, battle_result):
    """Add BM-0067 PvE audit/reward metadata to the canonical oasis report."""

    report = json.loads(_impl.build_oasis_report_content(attacker_city, oasis, battle_result))
    report["loot"] = battle_result.get("loot", {})
    report["pve"] = battle_result.get("pve", {})
    return json.dumps(report, sort_keys=True)
