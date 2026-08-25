"""Versioned PvE rules for final barbarian and oasis content.

BM-0067 versions PvE independently from ``balance.BALANCE_VERSION`` so final
barbarian/oasis tuning cannot rewrite historical combat or espionage seed
identities. Worlds persist the selected PvE rules version and the worker only
executes rules matching that persisted identity.

All neutral defenders use canonical BM-0063 unit keys. Legacy animal names such
as ``rat``/``spider`` are intentionally not part of this final catalogue because
the round combat engine has no canonical statistics for them.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from . import balance

PVE_RULES_VERSION = "2026.08.25-bm0067-v1"
PVE_TICK_SECONDS = 300

BARBARIANS_PER_10K_TILES = 50
OASES_PER_10K_TILES = 20
MIN_BARBARIANS_PER_WORLD = 8
MIN_OASES_PER_WORLD = 8

DIFFICULTY_ORDER = ("easy", "normal", "hard")
DIFFICULTY_THRESHOLDS = (0.50, 0.85)
OASIS_GUARD_REGEN_FRACTION_PER_TICK = 0.10
OASIS_CAPTURE_REQUIRES_LIVING_HERO = True

BARBARIAN_PROFILES: dict[str, dict[str, Any]] = {
    "easy": {
        "starting_resources": {resource: 750.0 for resource in balance.RESOURCE_FIELDS},
        "resource_regen_per_tick": 6.0,
        "population_max": 100,
        "buildings": (("town_hall", 1), ("barracks", 1), ("wall", 1)),
        "starting_troops": (("basic_infantry", 12), ("archer", 4), ("spy", 1)),
        "troop_caps": {"basic_infantry": 24, "archer": 8, "spy": 2},
        "recruits_per_tick": 1,
    },
    "normal": {
        "starting_resources": {resource: 1000.0 for resource in balance.RESOURCE_FIELDS},
        "resource_regen_per_tick": 10.0,
        "population_max": 120,
        "buildings": (("town_hall", 2), ("barracks", 2), ("wall", 2)),
        "starting_troops": (("basic_infantry", 20), ("archer", 10), ("spy", 2)),
        "troop_caps": {"basic_infantry": 40, "archer": 20, "spy": 4},
        "recruits_per_tick": 1,
    },
    "hard": {
        "starting_resources": {resource: 1500.0 for resource in balance.RESOURCE_FIELDS},
        "resource_regen_per_tick": 15.0,
        "population_max": 160,
        "buildings": (("town_hall", 3), ("barracks", 3), ("wall", 3), ("warehouse", 1)),
        "starting_troops": (
            ("basic_infantry", 25),
            ("heavy_infantry", 10),
            ("archer", 15),
            ("fast_cavalry", 5),
            ("spy", 3),
        ),
        "troop_caps": {
            "basic_infantry": 50,
            "heavy_infantry": 20,
            "archer": 30,
            "fast_cavalry": 10,
            "spy": 6,
        },
        "recruits_per_tick": 2,
    },
}

OASIS_PROFILES: dict[str, dict[str, Any]] = {
    "easy": {
        "bonus_percent": 25,
        "guard_target": {"basic_infantry": 8, "archer": 3},
    },
    "normal": {
        "bonus_percent": 25,
        "guard_target": {"basic_infantry": 14, "archer": 8, "fast_cavalry": 2},
    },
    "hard": {
        "bonus_percent": 50,
        "guard_target": {"heavy_infantry": 10, "archer": 12, "fast_cavalry": 5},
    },
}


def _stable_fraction(*parts: object) -> float:
    payload = ":".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def difficulty_for(
    *,
    world_id: int,
    x: int,
    y: int,
    kind: str,
    rules_version: str = PVE_RULES_VERSION,
) -> str:
    """Derive a stable difficulty tier from immutable world/coordinate data."""

    roll = _stable_fraction(rules_version, kind, int(world_id), int(x), int(y))
    if roll < DIFFICULTY_THRESHOLDS[0]:
        return "easy"
    if roll < DIFFICULTY_THRESHOLDS[1]:
        return "normal"
    return "hard"


def barbarian_profile(
    *, world_id: int, x: int, y: int, rules_version: str = PVE_RULES_VERSION
) -> tuple[str, dict[str, Any]]:
    difficulty = difficulty_for(
        world_id=world_id,
        x=x,
        y=y,
        kind="barbarian",
        rules_version=rules_version,
    )
    return difficulty, deepcopy(BARBARIAN_PROFILES[difficulty])


def oasis_profile(
    *, world_id: int, x: int, y: int, rules_version: str = PVE_RULES_VERSION
) -> tuple[str, dict[str, Any]]:
    difficulty = difficulty_for(
        world_id=world_id,
        x=x,
        y=y,
        kind="oasis",
        rules_version=rules_version,
    )
    return difficulty, deepcopy(OASIS_PROFILES[difficulty])


def world_content_counts(map_size: int) -> tuple[int, int]:
    """Scale neutral content density with map area while preserving small worlds."""

    side = max(int(map_size), 1)
    area = side * side
    barbarian_count = max(
        MIN_BARBARIANS_PER_WORLD,
        round((area / 10_000) * BARBARIANS_PER_10K_TILES),
    )
    oasis_count = max(
        MIN_OASES_PER_WORLD,
        round((area / 10_000) * OASES_PER_10K_TILES),
    )
    return barbarian_count, oasis_count


def rules_snapshot() -> dict[str, Any]:
    """Public exact contract consumed by generation, worker and UI/API clients."""

    return {
        "rules_version": PVE_RULES_VERSION,
        "tick_seconds": PVE_TICK_SECONDS,
        "difficulty_order": list(DIFFICULTY_ORDER),
        "difficulty_thresholds": list(DIFFICULTY_THRESHOLDS),
        "barbarians_per_10k_tiles": BARBARIANS_PER_10K_TILES,
        "oases_per_10k_tiles": OASES_PER_10K_TILES,
        "minimum_barbarians_per_world": MIN_BARBARIANS_PER_WORLD,
        "minimum_oases_per_world": MIN_OASES_PER_WORLD,
        "barbarian_profiles": deepcopy(BARBARIAN_PROFILES),
        "oasis_profiles": deepcopy(OASIS_PROFILES),
        "oasis_guard_regen_fraction_per_tick": OASIS_GUARD_REGEN_FRACTION_PER_TICK,
        "oasis_capture_requires_living_hero": OASIS_CAPTURE_REQUIRES_LIVING_HERO,
        "neutral_guards_use_canonical_units": True,
        "owned_oases_regenerate_neutral_guards": False,
    }
