"""Compatibility entrypoint for the BM-0064 deterministic combat engine.

The implementation lives in :mod:`combat_rounds`; this module keeps the
historic import path stable for movement, conquest, tests and external callers.
"""

import json

from . import combat_rounds as _impl
from . import pve_rules

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


def resolve_oasis_battle(*args, **kwargs):
    """Preserve BM-0064 scoring while attaching the pinned BM-0067 PvE rules."""

    attacker_city = args[0] if args else kwargs.get("attacker_city")
    oasis = args[1] if len(args) > 1 else kwargs.get("oasis")
    owner = getattr(attacker_city, "owner", None)
    previous_points = getattr(owner, "attacker_points", None) if owner else None
    result = _impl.resolve_oasis_battle(*args, **kwargs)
    if owner is not None and previous_points is not None:
        owner.attacker_points = previous_points

    if attacker_city is not None and oasis is not None:
        world = getattr(attacker_city, "world", None)
        rules_version = str(
            getattr(world, "pve_rules_version", None)
            or pve_rules.PVE_RULES_VERSION
        )
        difficulty = pve_rules.difficulty_for(
            world_id=oasis.world_id,
            x=oasis.x,
            y=oasis.y,
            kind="oasis",
            rules_version=rules_version,
        )
        result["pve_rules_version"] = rules_version
        result["pve_difficulty"] = difficulty
        result["oasis_resource_type"] = oasis.resource_type
        result["oasis_bonus_percent"] = int(oasis.bonus_percent)
        result["capture_requires_living_hero"] = (
            pve_rules.OASIS_CAPTURE_REQUIRES_LIVING_HERO
        )
    return result


def build_oasis_report_content(attacker_city, oasis, battle_result):
    """Add the exact BM-0067 rules identity to the BM-0064 combat report."""

    payload = json.loads(
        _impl.build_oasis_report_content(attacker_city, oasis, battle_result)
    )
    payload["pve"] = {
        "rules_version": battle_result.get(
            "pve_rules_version", pve_rules.PVE_RULES_VERSION
        ),
        "difficulty": battle_result.get("pve_difficulty"),
        "resource_type": oasis.resource_type,
        "bonus_percent": int(oasis.bonus_percent),
        "capture_requires_living_hero": bool(
            battle_result.get(
                "capture_requires_living_hero",
                pve_rules.OASIS_CAPTURE_REQUIRES_LIVING_HERO,
            )
        ),
        "neutral_guard_regeneration_fraction_per_tick": (
            pve_rules.OASIS_GUARD_REGEN_FRACTION_PER_TICK
        ),
    }
    return json.dumps(payload, sort_keys=True)
