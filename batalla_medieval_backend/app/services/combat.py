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
resolve_oasis_battle = _impl.resolve_oasis_battle
build_oasis_report_content = _impl.build_oasis_report_content
