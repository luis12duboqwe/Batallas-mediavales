from __future__ import annotations

import hashlib
import random
from copy import deepcopy
from datetime import timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import balance, hero as hero_service, hero_rules, production, world_lifecycle

# Compatibility alias for older imports/tests. Canonical numbers live in hero_rules.
DIFFICULTY_CONFIG = hero_rules.ADVENTURE_CONFIG


def _seed_hex(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _rng(seed: str) -> random.Random:
    return random.Random(int(seed, 16))


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def get_adventures(db: Session, hero_id: int) -> list[models.Adventure]:
    """Return adventures and deterministically replenish available choices."""

    hero = (
        db.query(models.Hero)
        .filter(models.Hero.id == hero_id)
        .with_for_update()
        .one_or_none()
    )
    if hero is None:
        db.rollback()
        raise ValueError("Hero not found")

    adventures = (
        db.query(models.Adventure)
        .filter(models.Adventure.hero_id == hero.id)
        .order_by(models.Adventure.id.asc())
        .all()
    )
    active_or_available = [row for row in adventures if row.status in {"available", "active"}]
    missing = max(0, hero_rules.ADVENTURE_ACTIVE_OR_AVAILABLE_TARGET - len(active_or_available))
    if missing:
        generation = len(adventures)
        seed = _seed_hex(hero_rules.HERO_RULES_VERSION, "adventure_generation", hero.id, hero.world_id, generation)
        seeded = _rng(seed)
        for _ in range(missing):
            difficulty = seeded.choice(hero_rules.ADVENTURE_DIFFICULTY_WEIGHTS)
            config = hero_rules.ADVENTURE_CONFIG[difficulty]
            row = models.Adventure(
                hero_id=hero.id,
                difficulty=difficulty,
                duration=int(config["duration"]),
                status="available",
                rules_version=hero_rules.HERO_RULES_VERSION,
            )
            db.add(row)
            adventures.append(row)
        db.commit()
        for row in adventures:
            if row.id is None:
                db.refresh(row)
    return adventures


def start_adventure(db: Session, adventure_id: int, hero: models.Hero) -> models.Adventure:
    """Start one adventure under a hero/adventure lock and persist its seed."""

    locked_hero = (
        db.query(models.Hero)
        .filter(models.Hero.id == hero.id, models.Hero.world_id == hero.world_id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    adv = (
        db.query(models.Adventure)
        .filter(models.Adventure.id == adventure_id, models.Adventure.hero_id == locked_hero.id)
        .with_for_update()
        .one_or_none()
    )
    if adv is None:
        db.rollback()
        raise ValueError("Adventure not found")
    if adv.status != "available":
        db.rollback()
        raise ValueError("Adventure not available")
    if locked_hero.status != "home":
        db.rollback()
        raise ValueError("Hero is busy")
    if locked_hero.health < hero_rules.HERO_MIN_ADVENTURE_HEALTH:
        db.rollback()
        raise ValueError("Hero is too injured")

    other_active = (
        db.query(models.Adventure)
        .filter(
            models.Adventure.hero_id == locked_hero.id,
            models.Adventure.status == "active",
            models.Adventure.id != adv.id,
        )
        .first()
    )
    if other_active:
        db.rollback()
        raise ValueError("Hero already has an active adventure")

    world_lifecycle.require_world_open(db, locked_hero.world_id)
    started_at = utc_now()
    adv.started_at = started_at
    adv.status = "active"
    adv.rules_version = hero_rules.HERO_RULES_VERSION
    adv.outcome_seed = _seed_hex(
        hero_rules.HERO_RULES_VERSION,
        "adventure_outcome",
        adv.id,
        locked_hero.id,
        locked_hero.world_id,
        adv.difficulty,
        started_at.isoformat(),
    )
    locked_hero.status = "adventure"
    db.add_all([adv, locked_hero])
    db.commit()
    db.refresh(adv)
    return adv


def _resource_loot(
    db: Session,
    hero: models.Hero,
    difficulty: str,
    seeded: random.Random,
) -> dict[str, Any] | None:
    if hero.city_id is None:
        return None
    city = (
        db.query(models.City)
        .filter(
            models.City.id == hero.city_id,
            models.City.world_id == hero.world_id,
            models.City.owner_id == hero.user_id,
        )
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if city is None:
        return None
    city, _ = production.recalculate_resources(db, city, return_gains=True, commit=False)
    resource = seeded.choice(list(balance.RESOURCE_FIELDS))
    config = hero_rules.ADVENTURE_CONFIG[difficulty]
    requested = seeded.randint(
        hero_rules.ADVENTURE_RESOURCE_MIN_AMOUNT,
        hero_rules.ADVENTURE_RESOURCE_MAX_AMOUNT,
    ) * int(config["resource_multiplier"])
    storage_limit = production.get_storage_limit(city)
    room = max(0, int(storage_limit - float(getattr(city, resource))))
    amount = min(requested, room)
    if amount <= 0:
        return None
    setattr(city, resource, float(getattr(city, resource)) + amount)
    db.add(city)
    return {"type": "resource", "resource": resource, "amount": amount}


def _item_loot(db: Session, hero: models.Hero, seeded: random.Random) -> dict[str, Any] | None:
    templates = db.query(models.ItemTemplate).order_by(models.ItemTemplate.id.asc()).all()
    if not templates:
        return None
    template = seeded.choice(templates)
    item = models.HeroItem(hero_id=hero.id, template_id=template.id, is_equipped=False)
    db.add(item)
    return {"type": "item", "name": template.name, "rarity": template.rarity}


def claim_adventure(db: Session, adventure_id: int, hero: models.Hero) -> dict[str, Any]:
    """Resolve and pay an adventure once; committed retries replay stored result."""

    locked_hero = (
        db.query(models.Hero)
        .filter(models.Hero.id == hero.id, models.Hero.world_id == hero.world_id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    adv = (
        db.query(models.Adventure)
        .filter(models.Adventure.id == adventure_id, models.Adventure.hero_id == locked_hero.id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if adv is None:
        db.rollback()
        raise ValueError("Adventure not found")
    if adv.result is not None and adv.status in {"completed", "failed"}:
        return deepcopy(adv.result)
    world_lifecycle.require_world_open(db, locked_hero.world_id)
    if adv.status != "active":
        db.rollback()
        raise ValueError("Adventure not active")
    started_at = _aware(adv.started_at)
    if started_at is None:
        db.rollback()
        raise ValueError("Adventure has no start time")
    now = utc_now()
    if now < started_at + timedelta(seconds=adv.duration):
        db.rollback()
        raise ValueError("Adventure not finished yet")

    config = hero_rules.ADVENTURE_CONFIG.get(adv.difficulty)
    if config is None:
        db.rollback()
        raise ValueError("Unknown adventure difficulty")
    seed = adv.outcome_seed or _seed_hex(
        hero_rules.HERO_RULES_VERSION,
        "adventure_outcome",
        adv.id,
        locked_hero.id,
        locked_hero.world_id,
        adv.difficulty,
        started_at.isoformat(),
    )
    seeded = _rng(seed)
    raw_damage = seeded.randint(int(config["damage_min"]), int(config["damage_max"]))
    defense_reduction = locked_hero.defense_points // 10
    damage = max(1, raw_damage - defense_reduction)
    locked_hero.health = max(0.0, locked_hero.health - damage)

    loot: dict[str, Any] | None = None
    xp_gained = 0
    if locked_hero.health <= 0:
        locked_hero.status = "dead"
        adv.status = "failed"
        status = "dead"
    else:
        locked_hero.status = "home"
        adv.status = "completed"
        status = "success"
        xp_gained = int(config["xp"])
        hero_service.add_xp(db, locked_hero, xp_gained, commit=False)
        roll = seeded.random()
        if roll < hero_rules.ADVENTURE_ITEM_LOOT_CHANCE:
            loot = _item_loot(db, locked_hero, seeded)
        elif roll < hero_rules.ADVENTURE_ITEM_LOOT_CHANCE + hero_rules.ADVENTURE_RESOURCE_LOOT_CHANCE:
            loot = _resource_loot(db, locked_hero, adv.difficulty, seeded)

    result: dict[str, Any] = {
        "status": status,
        "damage": int(damage),
        "xp": xp_gained,
        "loot": loot,
        "rules_version": hero_rules.HERO_RULES_VERSION,
        "seed": seed,
    }
    adv.rules_version = hero_rules.HERO_RULES_VERSION
    adv.outcome_seed = seed
    adv.result = result
    adv.completed_at = now
    db.add_all([adv, locked_hero])
    db.commit()
    return deepcopy(result)
