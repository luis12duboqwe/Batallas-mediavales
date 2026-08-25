"""Versioned deterministic PvE generation, difficulty and regeneration.

BM-0067 keeps the rules of a running world pinned in ``World.special_rules`` so
future deployments cannot silently reroll difficulty. The manifest also stores
coordinate -> tier assignments and the last five-minute regeneration bucket,
which makes the periodic job idempotent without adding schema columns.

Combat numbers still come from the canonical unit catalog in ``balance``. Oasis
guards deliberately use real game units; the legacy ``rat``/``spider`` payloads
had no combat statistics and therefore provided zero defense.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import balance, production

PVE_RULES_VERSION = "2026.08.25-bm0067-v1"
PVE_TICK_SECONDS = 300
PVE_BARBARIAN_TARGET_ACTIVE = 8
PVE_OASIS_TARGET_TOTAL = 20
PVE_TIERS = (1, 2, 3)

# Difficulty profiles only compose canonical game resources/buildings/units.
# Tier 1 intentionally matches the pre-BM-0067 barbarian baseline.
BARBARIAN_PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "resources": deepcopy(balance.BARBARIAN_STARTING_RESOURCES),
        "buildings": dict(balance.BARBARIAN_STARTING_BUILDINGS),
        "troops": dict(balance.BARBARIAN_STARTING_TROOPS),
        "resource_regen": balance.BARBARIAN_RESOURCE_GROWTH_AMOUNT,
    },
    2: {
        "resources": {
            resource: float(amount) * 1.6
            for resource, amount in balance.BARBARIAN_STARTING_RESOURCES.items()
        },
        "buildings": {"town_hall": 3, "barracks": 3, "wall": 3},
        "troops": {
            "basic_infantry": 32,
            "heavy_infantry": 6,
            "archer": 18,
            "spy": 3,
        },
        "resource_regen": balance.BARBARIAN_RESOURCE_GROWTH_AMOUNT * 2,
    },
    3: {
        "resources": {
            resource: float(amount) * 2.5
            for resource, amount in balance.BARBARIAN_STARTING_RESOURCES.items()
        },
        "buildings": {"town_hall": 5, "barracks": 5, "wall": 5},
        "troops": {
            "basic_infantry": 45,
            "heavy_infantry": 14,
            "archer": 28,
            "fast_cavalry": 6,
            "spy": 4,
        },
        "resource_regen": balance.BARBARIAN_RESOURCE_GROWTH_AMOUNT * 3,
    },
}

OASIS_PROFILES: dict[int, dict[str, Any]] = {
    1: {
        "bonus_percent": 25,
        "guards": {"basic_infantry": 10, "archer": 5},
        "conquest_reward": 150,
        "regeneration_fraction": 0.20,
    },
    2: {
        "bonus_percent": 35,
        "guards": {
            "basic_infantry": 20,
            "heavy_infantry": 5,
            "archer": 12,
        },
        "conquest_reward": 300,
        "regeneration_fraction": 0.15,
    },
    3: {
        "bonus_percent": 50,
        "guards": {
            "heavy_infantry": 20,
            "archer": 20,
            "fast_cavalry": 8,
        },
        "conquest_reward": 600,
        "regeneration_fraction": 0.10,
    },
}

_BARBARian_TIER_PATTERN = (1, 1, 1, 2, 2, 2, 3, 3)
_OASIS_TIER_PATTERN = (1, 1, 1, 2, 2, 3)


def _coord_key(x: int, y: int) -> str:
    return f"{int(x)},{int(y)}"


def _decode_special_rules(raw: str | None) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {"legacy": text}
    return parsed if isinstance(parsed, dict) else {"legacy": parsed}


def _manifest(world: models.World) -> tuple[dict[str, Any], dict[str, Any]]:
    rules = _decode_special_rules(world.special_rules)
    pve = rules.setdefault("pve", {})
    if not isinstance(pve, dict):
        pve = {}
        rules["pve"] = pve

    version = pve.get("version")
    if version not in (None, "", PVE_RULES_VERSION):
        raise RuntimeError(f"Unsupported PvE rules version for world {world.id}: {version}")
    pve["version"] = PVE_RULES_VERSION
    pve.setdefault("barbarian_tiers", {})
    pve.setdefault("oasis_tiers", {})
    return rules, pve


def _persist_manifest(world: models.World, rules: dict[str, Any]) -> None:
    world.special_rules = json.dumps(rules, sort_keys=True, separators=(",", ":"))


def world_rules_version(world: models.World) -> str:
    _, pve = _manifest(world)
    return str(pve["version"])


def _stable_tier(world: models.World, kind: str, x: int, y: int) -> int:
    payload = f"{PVE_RULES_VERSION}:{world.name}:{world.map_size}:{kind}:{x}:{y}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % 8
    if bucket < 4:
        return 1
    if bucket < 7:
        return 2
    return 3


def _tier_for_coordinate(
    world: models.World,
    *,
    kind: str,
    x: int,
    y: int,
    index: int | None = None,
    pve: dict[str, Any] | None = None,
) -> int:
    if pve is None:
        _, pve = _manifest(world)
    mapping_name = "barbarian_tiers" if kind == "barbarian" else "oasis_tiers"
    mapping = pve.setdefault(mapping_name, {})
    key = _coord_key(x, y)
    if key in mapping:
        tier = int(mapping[key])
        if tier in PVE_TIERS:
            return tier

    pattern = _BARBARian_TIER_PATTERN if kind == "barbarian" else _OASIS_TIER_PATTERN
    tier = pattern[(index - 1) % len(pattern)] if index else _stable_tier(world, kind, x, y)
    mapping[key] = tier
    return tier


def barbarian_tier(city: models.City) -> int | None:
    world = city.world
    if world is None:
        return None
    rules, pve = _manifest(world)
    key = _coord_key(city.x, city.y)
    existing = pve.get("barbarian_tiers", {}).get(key)
    if existing is None and city.owner_id is not None:
        return None
    tier = _tier_for_coordinate(world, kind="barbarian", x=city.x, y=city.y, pve=pve)
    if world.special_rules != json.dumps(rules, sort_keys=True, separators=(",", ":")):
        _persist_manifest(world, rules)
    return tier


def oasis_tier(oasis: models.Oasis) -> int:
    world = oasis.world
    if world is None:
        return 1
    rules, pve = _manifest(world)
    tier = _tier_for_coordinate(world, kind="oasis", x=oasis.x, y=oasis.y, pve=pve)
    if world.special_rules != json.dumps(rules, sort_keys=True, separators=(",", ":")):
        _persist_manifest(world, rules)
    return tier


def oasis_profile(oasis: models.Oasis) -> dict[str, Any]:
    return deepcopy(OASIS_PROFILES[oasis_tier(oasis)])


def oasis_conquest_reward(oasis: models.Oasis) -> dict[str, int]:
    profile = oasis_profile(oasis)
    resource = oasis.resource_type if oasis.resource_type in balance.RESOURCE_FIELDS else "wood"
    return {resource: int(profile["conquest_reward"])}


def _canonicalize_oasis_guards(oasis: models.Oasis, profile: dict[str, Any]) -> None:
    current = oasis.troops if isinstance(oasis.troops, dict) else {}
    canonical = {
        unit: max(int(amount), 0)
        for unit, amount in current.items()
        if unit in balance.UNIT_COMBAT_STATS and int(amount) > 0
    }
    # A legacy animal-only oasis had zero effective defense. Upgrade that invalid
    # state atomically to the versioned guard baseline rather than leave it free.
    if not canonical and current:
        canonical = deepcopy(profile["guards"])
    oasis.troops = canonical


def _create_barbarian(
    db: Session,
    world: models.World,
    *,
    x: int,
    y: int,
    tier: int,
    ordinal: int,
) -> models.City:
    from .world_gen import get_tile_type

    profile = BARBARIAN_PROFILES[tier]
    city = models.City(
        name=f"Aldea Bárbara T{tier}-{ordinal:02d}",
        owner_id=None,
        world_id=world.id,
        x=x,
        y=y,
        population_max=balance.BARBARIAN_POPULATION_MAX,
        loyalty=balance.LOYALTY_MAX,
        tile_type=get_tile_type(x, y),
        **{resource: float(profile["resources"][resource]) for resource in balance.RESOURCE_FIELDS},
    )
    db.add(city)
    db.flush()
    for building, level in profile["buildings"].items():
        db.add(models.Building(city_id=city.id, name=building, level=int(level)))
    for unit, quantity in profile["troops"].items():
        db.add(models.Troop(city_id=city.id, unit_type=unit, quantity=int(quantity)))
    return city


def _create_oasis(
    db: Session,
    world: models.World,
    *,
    x: int,
    y: int,
    tier: int,
    ordinal: int,
) -> models.Oasis:
    rng = random.Random(
        hashlib.sha256(
            f"{PVE_RULES_VERSION}:{world.name}:oasis:{ordinal}:{x}:{y}".encode("utf-8")
        ).hexdigest()
    )
    profile = OASIS_PROFILES[tier]
    oasis = models.Oasis(
        world_id=world.id,
        x=x,
        y=y,
        resource_type=rng.choice(list(balance.RESOURCE_FIELDS)),
        bonus_percent=int(profile["bonus_percent"]),
        troops=deepcopy(profile["guards"]),
    )
    db.add(oasis)
    return oasis


def _occupied_coordinates(db: Session, world_id: int) -> set[tuple[int, int]]:
    city_coords = set(
        db.query(models.City.x, models.City.y)
        .filter(models.City.world_id == world_id)
        .all()
    )
    oasis_coords = set(
        db.query(models.Oasis.x, models.Oasis.y)
        .filter(models.Oasis.world_id == world_id)
        .all()
    )
    return {(int(x), int(y)) for x, y in city_coords | oasis_coords}


def _candidate_coordinates(
    db: Session,
    world: models.World,
    *,
    kind: str,
) -> Iterable[tuple[int, int]]:
    from .world_gen import get_tile_type

    rng = random.Random(f"{PVE_RULES_VERSION}:{world.name}:{world.map_size}:{kind}")
    occupied = _occupied_coordinates(db, world.id)
    attempts = max(int(world.map_size) ** 2 * 4, 2000)
    for _ in range(attempts):
        x = rng.randrange(max(int(world.map_size), 1))
        y = rng.randrange(max(int(world.map_size), 1))
        coord = (x, y)
        if coord in occupied or get_tile_type(x, y) == "water":
            continue
        occupied.add(coord)
        yield coord


def ensure_world_pve(
    db: Session,
    world: models.World,
    *,
    canonical_barbarian_coords: Iterable[tuple[int, int]] | None = None,
) -> dict[str, int]:
    """Idempotently ensure one world has the final PvE population.

    Existing progress is never reset. Conquered barbarian-origin cities remain
    player-owned; if active barbarian count drops below the target a replacement
    is generated on a fresh coordinate. Oases are a fixed world resource: owned
    oases count toward the total and are never duplicated by regeneration.
    """

    rules, pve = _manifest(world)
    created_barbarians = 0
    created_oases = 0

    canonical = list(canonical_barbarian_coords or [])
    for index, (x, y) in enumerate(canonical, start=1):
        key = _coord_key(x, y)
        existing = (
            db.query(models.City)
            .filter(models.City.world_id == world.id, models.City.x == x, models.City.y == y)
            .one_or_none()
        )
        tier = _tier_for_coordinate(
            world, kind="barbarian", x=x, y=y, index=index, pve=pve
        )
        if existing is not None:
            was_known = key in pve.get("barbarian_tiers", {})
            looks_barbarian = str(existing.name or "").startswith("Aldea Bárbara")
            if existing.owner_id is not None and not (was_known or looks_barbarian):
                raise RuntimeError(
                    "Canonical PvE coordinate is occupied by a player city: "
                    f"world={world.id} x={x} y={y}"
                )
            continue
        _create_barbarian(db, world, x=x, y=y, tier=tier, ordinal=index)
        created_barbarians += 1

    active_barbarians = (
        db.query(models.City)
        .filter(models.City.world_id == world.id, models.City.owner_id.is_(None))
        .order_by(models.City.id.asc())
        .all()
    )
    for index, city in enumerate(active_barbarians, start=1):
        _tier_for_coordinate(
            world,
            kind="barbarian",
            x=city.x,
            y=city.y,
            index=index,
            pve=pve,
        )

    needed = max(PVE_BARBARIAN_TARGET_ACTIVE - len(active_barbarians), 0)
    if needed:
        candidates = _candidate_coordinates(db, world, kind="barbarian-respawn")
        start = len(pve.get("barbarian_tiers", {})) + 1
        for offset in range(needed):
            try:
                x, y = next(candidates)
            except StopIteration as exc:
                raise RuntimeError("World has no free coordinate for barbarian regeneration") from exc
            ordinal = start + offset
            tier = _tier_for_coordinate(
                world,
                kind="barbarian",
                x=x,
                y=y,
                index=ordinal,
                pve=pve,
            )
            _create_barbarian(db, world, x=x, y=y, tier=tier, ordinal=ordinal)
            created_barbarians += 1

    oases = (
        db.query(models.Oasis)
        .filter(models.Oasis.world_id == world.id)
        .order_by(models.Oasis.id.asc())
        .all()
    )
    for index, oasis in enumerate(oases, start=1):
        tier = _tier_for_coordinate(
            world,
            kind="oasis",
            x=oasis.x,
            y=oasis.y,
            index=index,
            pve=pve,
        )
        profile = OASIS_PROFILES[tier]
        if oasis.owner_city_id is None:
            _canonicalize_oasis_guards(oasis, profile)
            if int(oasis.bonus_percent or 0) not in {25, 35, 50}:
                oasis.bonus_percent = int(profile["bonus_percent"])

    oasis_needed = max(PVE_OASIS_TARGET_TOTAL - len(oases), 0)
    if oasis_needed:
        candidates = _candidate_coordinates(db, world, kind="oasis")
        start = len(oases) + 1
        for offset in range(oasis_needed):
            try:
                x, y = next(candidates)
            except StopIteration as exc:
                raise RuntimeError("World has no free coordinate for oasis generation") from exc
            ordinal = start + offset
            tier = _tier_for_coordinate(
                world,
                kind="oasis",
                x=x,
                y=y,
                index=ordinal,
                pve=pve,
            )
            _create_oasis(db, world, x=x, y=y, tier=tier, ordinal=ordinal)
            created_oases += 1

    _persist_manifest(world, rules)
    db.add(world)
    db.flush()
    return {"barbarians_created": created_barbarians, "oases_created": created_oases}


def _tick_bucket(now: datetime) -> int:
    aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return int(aware.timestamp()) // PVE_TICK_SECONDS


def _tick_rng(world_id: int, bucket: int, kind: str, entity_id: int) -> random.Random:
    seed = hashlib.sha256(
        f"{PVE_RULES_VERSION}:{world_id}:{bucket}:{kind}:{entity_id}".encode("utf-8")
    ).hexdigest()
    return random.Random(seed)


def _regenerate_barbarian(
    db: Session, city: models.City, tier: int, bucket: int
) -> None:
    profile = BARBARIAN_PROFILES[tier]
    rng = _tick_rng(city.world_id, bucket, "barbarian", city.id)

    if rng.random() < balance.BARBARIAN_RESOURCE_GROWTH_CHANCE:
        storage_limit = production.get_storage_limit(city)
        for resource in balance.RESOURCE_FIELDS:
            ceiling = min(
                float(profile["resources"][resource]) * 2.0,
                float(storage_limit),
            )
            current = float(getattr(city, resource))
            setattr(
                city,
                resource,
                min(current + float(profile["resource_regen"]), ceiling),
            )

    if rng.random() >= balance.BARBARIAN_RECRUIT_CHANCE:
        return

    target_troops = profile["troops"]
    recruitable = [
        unit
        for unit in sorted(target_troops)
        if unit != "spy" and unit in balance.UNIT_CATALOG
    ]
    if not recruitable:
        return
    unit = recruitable[rng.randrange(len(recruitable))]
    current_row = next((row for row in city.troops if row.unit_type == unit), None)
    current_quantity = int(current_row.quantity) if current_row else 0
    ceiling = max(int(target_troops[unit]) * 2, 1)
    if current_quantity >= ceiling:
        return

    cost = balance.UNIT_CATALOG[unit]["training_cost"]
    if not production.check_cost(city, cost):
        return
    production.pay_cost(city, cost)
    if current_row:
        current_row.quantity += 1
    else:
        db.add(models.Troop(city_id=city.id, unit_type=unit, quantity=1))


def _regenerate_oasis(oasis: models.Oasis, tier: int) -> None:
    if oasis.owner_city_id is not None:
        return
    profile = OASIS_PROFILES[tier]
    _canonicalize_oasis_guards(oasis, profile)
    current = dict(oasis.troops or {})
    target = profile["guards"]
    fraction = float(profile["regeneration_fraction"])
    for unit, target_amount in target.items():
        amount = max(int(current.get(unit, 0)), 0)
        if amount >= int(target_amount):
            continue
        step = max(1, int(math.ceil(int(target_amount) * fraction)))
        current[unit] = min(int(target_amount), amount + step)
    oasis.troops = current


def process_pve_tick(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Run one idempotent five-minute PvE regeneration bucket per active world."""

    tick_now = now or utc_now()
    bucket = _tick_bucket(tick_now)
    processed_worlds = 0
    regenerated_barbarians = 0
    regenerated_oases = 0

    worlds = (
        db.query(models.World)
        .filter(models.World.is_active.is_(True))
        .order_by(models.World.id.asc())
        .with_for_update()
        .all()
    )
    for world in worlds:
        ensure_world_pve(db, world)
        rules, manifest = _manifest(world)
        if int(manifest.get("last_tick_bucket", -1)) >= bucket:
            continue

        barbarians = (
            db.query(models.City)
            .filter(models.City.world_id == world.id, models.City.owner_id.is_(None))
            .order_by(models.City.id.asc())
            .all()
        )
        for city in barbarians:
            tier = _tier_for_coordinate(
                world,
                kind="barbarian",
                x=city.x,
                y=city.y,
                pve=manifest,
            )
            _regenerate_barbarian(db, city, tier, bucket)
            regenerated_barbarians += 1

        oases = (
            db.query(models.Oasis)
            .filter(models.Oasis.world_id == world.id)
            .order_by(models.Oasis.id.asc())
            .all()
        )
        for oasis in oases:
            if oasis.owner_city_id is not None:
                continue
            tier = _tier_for_coordinate(
                world,
                kind="oasis",
                x=oasis.x,
                y=oasis.y,
                pve=manifest,
            )
            _regenerate_oasis(oasis, tier)
            regenerated_oases += 1

        manifest["last_tick_bucket"] = bucket
        _persist_manifest(world, rules)
        db.add(world)
        processed_worlds += 1

    db.flush()
    return {
        "worlds_processed": processed_worlds,
        "barbarians_regenerated": regenerated_barbarians,
        "oases_regenerated": regenerated_oases,
        "tick_bucket": bucket,
    }
