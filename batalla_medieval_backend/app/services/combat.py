"""Compatibility entrypoint for the BM-0064 deterministic combat engine.

The implementation lives in :mod:`combat_rounds`; this module keeps the
historic import path stable for movement, conquest, tests and external callers.
"""

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


def resolve_oasis_battle(*args, **kwargs):
    """Preserve the pre-BM-0064 oasis scoring contract.

    BM-0064 changes combat determinism/rounds only. Oasis combat historically
    returned ``xp_gained`` for the hero but did not award player attacker
    ranking points, so keep that boundary stable here.
    """

    attacker_city = args[0] if args else kwargs.get("attacker_city")
    owner = getattr(attacker_city, "owner", None)
    previous_points = getattr(owner, "attacker_points", None) if owner else None
    result = _impl.resolve_oasis_battle(*args, **kwargs)
    if owner is not None and previous_points is not None:
        owner.attacker_points = previous_points
    return result


build_oasis_report_content = _impl.build_oasis_report_content
