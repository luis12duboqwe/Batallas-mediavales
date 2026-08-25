"""Deterministic BM-0067 barbarian and oasis regeneration worker."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import balance, production, pve_rules

logger = logging.getLogger(__name__)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _tick_bucket(value: datetime) -> int:
    return int(value.timestamp()) // pve_rules.PVE_TICK_SECONDS


def _troop_by_type(city: models.City, unit_type: str) -> models.Troop | None:
    return next((troop for troop in city.troops if troop.unit_type == unit_type), None)


def _regenerate_barbarian(db: Session, city: models.City, rules_version: str) -> int:
    """Advance one unowned barbarian city toward its bounded difficulty profile."""

    _, profile = pve_rules.barbarian_profile(
        world_id=city.world_id,
        x=city.x,
        y=city.y,
        rules_version=rules_version,
    )
    storage_limit = production.get_storage_limit(city)
    resource_gain = max(float(profile["resource_regen_per_tick"]), 0.0)
    for resource in balance.RESOURCE_FIELDS:
        current = max(float(getattr(city, resource)), 0.0)
        setattr(city, resource, min(current + resource_gain, storage_limit))

    recruited = 0
    recruit_budget = max(int(profile["recruits_per_tick"]), 0)
    caps: dict[str, int] = profile["troop_caps"]
    for unit_type, cap in caps.items():
        if recruited >= recruit_budget:
            break
        if unit_type not in balance.UNIT_CATALOG:
            raise RuntimeError(f"PvE profile contains unknown unit: {unit_type}")

        troop = _troop_by_type(city, unit_type)
        current = max(int(troop.quantity), 0) if troop else 0
        missing = max(int(cap) - current, 0)
        while missing > 0 and recruited < recruit_budget:
            cost = balance.UNIT_CATALOG[unit_type]["training_cost"]
            if not production.check_cost(city, cost):
                return recruited
            production.pay_cost(city, cost)
            if troop is None:
                troop = models.Troop(city_id=city.id, unit_type=unit_type, quantity=0)
                db.add(troop)
                city.troops.append(troop)
            troop.quantity += 1
            current += 1
            missing -= 1
            recruited += 1
    return recruited


def _regenerate_oasis(oasis: models.Oasis, rules_version: str) -> int:
    """Regenerate only neutral guards; player-owned oasis state is untouched."""

    if oasis.owner_city_id is not None:
        return 0

    _, profile = pve_rules.oasis_profile(
        world_id=oasis.world_id,
        x=oasis.x,
        y=oasis.y,
        rules_version=rules_version,
    )
    target: dict[str, int] = profile["guard_target"]
    current_raw = dict(oasis.troops or {})
    # Drop pre-BM-0067 animal aliases with no canonical combat statistics.
    current = {
        unit: max(int(current_raw.get(unit, 0) or 0), 0)
        for unit in target
    }

    regenerated = 0
    for unit_type, target_amount in target.items():
        if unit_type not in balance.UNIT_COMBAT_STATS:
            raise RuntimeError(f"Oasis profile contains unknown combat unit: {unit_type}")
        target_amount = max(int(target_amount), 0)
        amount = current.get(unit_type, 0)
        if amount >= target_amount:
            continue
        step = max(
            1,
            int(math.ceil(target_amount * pve_rules.OASIS_GUARD_REGEN_FRACTION_PER_TICK)),
        )
        added = min(step, target_amount - amount)
        current[unit_type] = amount + added
        regenerated += added

    oasis.troops = {unit: amount for unit, amount in current.items() if amount > 0}
    return regenerated


def _process_world_tick(db: Session, world_id: int, now: datetime) -> dict[str, int | bool]:
    world = (
        db.query(models.World)
        .filter(models.World.id == world_id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    if not world.is_active:
        return {"processed": False, "barbarians": 0, "recruited": 0, "oases": 0, "guards": 0}

    rules_version = str(world.pve_rules_version or "")
    if rules_version != pve_rules.PVE_RULES_VERSION:
        logger.warning(
            "Skipping unsupported PvE rules version world=%s version=%s current=%s",
            world.id,
            rules_version,
            pve_rules.PVE_RULES_VERSION,
        )
        return {"processed": False, "barbarians": 0, "recruited": 0, "oases": 0, "guards": 0}

    last_tick = _aware(world.pve_last_tick_at)
    if last_tick is not None and _tick_bucket(last_tick) >= _tick_bucket(now):
        return {"processed": False, "barbarians": 0, "recruited": 0, "oases": 0, "guards": 0}

    barbarians = (
        db.query(models.City)
        .filter(
            models.City.world_id == world.id,
            models.City.owner_id.is_(None),
        )
        .order_by(models.City.id.asc())
        .with_for_update()
        .all()
    )
    recruited = sum(
        _regenerate_barbarian(db, city, rules_version)
        for city in barbarians
    )

    oases = (
        db.query(models.Oasis)
        .filter(
            models.Oasis.world_id == world.id,
            models.Oasis.owner_city_id.is_(None),
        )
        .order_by(models.Oasis.id.asc())
        .with_for_update()
        .all()
    )
    guards = sum(_regenerate_oasis(oasis, rules_version) for oasis in oases)

    world.pve_last_tick_at = now
    db.add(world)
    db.flush()
    return {
        "processed": True,
        "barbarians": len(barbarians),
        "recruited": recruited,
        "oases": len(oases),
        "guards": guards,
    }


def process_barbarian_growth(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """Advance every active world by at most one durable five-minute PvE tick.

    The scheduler already guarantees one worker owns the job globally. The
    per-world row lock plus ``pve_last_tick_at`` additionally makes retries and
    restarts idempotent at the domain level.
    """

    tick_time = _aware(now or utc_now()) or utc_now()
    world_ids = [
        int(world_id)
        for (world_id,) in (
            db.query(models.World.id)
            .filter(models.World.is_active.is_(True))
            .order_by(models.World.id.asc())
            .all()
        )
    ]
    totals = {
        "worlds": 0,
        "barbarians": 0,
        "recruited": 0,
        "oases": 0,
        "guards": 0,
    }
    for world_id in world_ids:
        result = _process_world_tick(db, world_id, tick_time)
        if not result["processed"]:
            continue
        totals["worlds"] += 1
        for key in ("barbarians", "recruited", "oases", "guards"):
            totals[key] += int(result[key])
    return totals
