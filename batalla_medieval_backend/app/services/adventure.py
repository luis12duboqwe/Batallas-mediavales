"""Deterministic, retry-safe adventures for the BM-0068 hero package."""

from __future__ import annotations

import hashlib
import math
import random
from copy import deepcopy
from datetime import timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import balance, hero as hero_service, hero_rules, production


def _ensure_timezone(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _hero_from_value(db: Session, hero: models.Hero | int) -> models.Hero:
    hero_id = hero.id if isinstance(hero, models.Hero) else int(hero)
    return hero_service.lock_hero_for_update(db, hero_id)


def _seed_for(
    *, world_id: int, hero_id: int, generation: int, slot: int, difficulty: str
) -> str:
    payload = (
        f"{hero_rules.HERO_RULES_VERSION}:{world_id}:{hero_id}:"
        f"generation={generation}:slot={slot}:difficulty={difficulty}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _difficulty_for(*, world_id: int, hero_id: int, generation: int, slot: int) -> str:
    payload = (
        f"{hero_rules.HERO_RULES_VERSION}:{world_id}:{hero_id}:"
        f"generation={generation}:slot={slot}:difficulty"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % len(hero_rules.ADVENTURE_DIFFICULTY_PATTERN)
    return hero_rules.ADVENTURE_DIFFICULTY_PATTERN[index]


def _lock_adventure(db: Session, adventure_id: int) -> models.Adventure:
    adventure = (
        db.query(models.Adventure)
        .filter(models.Adventure.id == adventure_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if adventure is None:
        raise ValueError("Adventure not found")
    return adventure


def get_adventures(
    db: Session, hero: models.Hero | int
) -> list[models.Adventure]:
    """Return the package queue, creating one deterministic batch when empty."""

    locked_hero = _hero_from_value(db, hero)
    active = (
        db.query(models.Adventure)
        .filter(
            models.Adventure.hero_id == locked_hero.id,
            models.Adventure.status.in_(["available", "active"]),
        )
        .order_by(models.Adventure.id.asc())
        .all()
    )
    if not active:
        total = (
            db.query(models.Adventure)
            .filter(models.Adventure.hero_id == locked_hero.id)
            .count()
        )
        generation = total // hero_rules.HERO_ADVENTURES_PER_BATCH
        created: list[models.Adventure] = []
        for slot in range(hero_rules.HERO_ADVENTURES_PER_BATCH):
            difficulty = _difficulty_for(
                world_id=locked_hero.world_id,
                hero_id=locked_hero.id,
                generation=generation,
                slot=slot,
            )
            config = hero_rules.ADVENTURE_DIFFICULTIES[difficulty]
            adventure = models.Adventure(
                hero_id=locked_hero.id,
                difficulty=difficulty,
                duration=int(config["duration_seconds"]),
                status="available",
                rules_version=hero_rules.HERO_RULES_VERSION,
                seed=_seed_for(
                    world_id=locked_hero.world_id,
                    hero_id=locked_hero.id,
                    generation=generation,
                    slot=slot,
                    difficulty=difficulty,
                ),
            )
            db.add(adventure)
            created.append(adventure)
        db.commit()
        for adventure in created:
            db.refresh(adventure)
        active = created

    recent_finished = (
        db.query(models.Adventure)
        .filter(
            models.Adventure.hero_id == locked_hero.id,
            models.Adventure.status.in_(["completed", "failed"]),
        )
        .order_by(models.Adventure.id.desc())
        .limit(5)
        .all()
    )
    return list(active) + list(recent_finished)


def start_adventure(
    db: Session, adventure_id: int, hero: models.Hero
) -> models.Adventure:
    adventure = _lock_adventure(db, adventure_id)
    if adventure.hero_id != hero.id:
        raise ValueError("Not your adventure")
    if adventure.rules_version != hero_rules.HERO_RULES_VERSION:
        raise ValueError("Adventure rules version is not supported")
    if adventure.status != "available":
        raise ValueError("Adventure not available")

    locked_hero = hero_service.lock_hero_for_update(db, hero.id)
    if locked_hero.status != "home":
        raise ValueError("Hero is busy")
    if float(locked_hero.health) < hero_rules.HERO_MIN_ADVENTURE_HEALTH:
        raise ValueError("Hero is too injured")

    bonuses = hero_service.calculate_total_bonuses(locked_hero)
    base_duration = int(
        hero_rules.ADVENTURE_DIFFICULTIES[adventure.difficulty]["duration_seconds"]
    )
    adventure.duration = max(
        1,
        int(math.ceil(base_duration * (1.0 - bonuses["speed"]))),
    )
    adventure.status = "active"
    adventure.started_at = utc_now()
    locked_hero.status = "adventure"
    db.add_all([adventure, locked_hero])
    db.commit()
    db.refresh(adventure)
    return adventure


def claim_adventure(
    db: Session, adventure_id: int, hero: models.Hero
) -> dict[str, Any]:
    """Claim exactly once; retries return the persisted outcome verbatim."""

    adventure = _lock_adventure(db, adventure_id)
    if adventure.hero_id != hero.id:
        raise ValueError("Not your adventure")
    if adventure.rules_version != hero_rules.HERO_RULES_VERSION:
        raise ValueError("Adventure rules version is not supported")
    if adventure.status in {"completed", "failed"} and adventure.result_json:
        return deepcopy(adventure.result_json)
    if adventure.status != "active":
        raise ValueError("Adventure not active")
    if adventure.started_at is None:
        raise ValueError("Adventure start time is missing")

    now = utc_now()
    end_time = _ensure_timezone(adventure.started_at) + timedelta(
        seconds=int(adventure.duration)
    )
    if now < end_time:
        raise ValueError("Adventure not finished yet")

    locked_hero = hero_service.lock_hero_for_update(db, hero.id)
    rng = random.Random(int(adventure.seed, 16))
    config = hero_rules.ADVENTURE_DIFFICULTIES[adventure.difficulty]
    bonuses = hero_service.calculate_total_bonuses(locked_hero)

    raw_damage = rng.randint(int(config["damage_min"]), int(config["damage_max"]))
    damage = max(1, int(round(raw_damage * (1.0 - bonuses["defense"]))))
    locked_hero.health = max(0.0, float(locked_hero.health) - damage)

    if locked_hero.health <= 0:
        locked_hero.status = "dead"
        adventure.status = "failed"
        adventure.completed_at = now
        result = {
            "rules_version": hero_rules.HERO_RULES_VERSION,
            "seed": adventure.seed,
            "status": "dead",
            "damage": damage,
            "xp": 0,
            "loot": None,
        }
        adventure.result_json = result
        db.add_all([adventure, locked_hero])
        db.commit()
        return deepcopy(result)

    locked_hero.status = "home"
    adventure.status = "completed"
    adventure.completed_at = now

    xp_gained = max(
        1,
        int(round(float(config["base_xp"]) * (1.0 + bonuses["attack"]))),
    )
    hero_service.add_xp(locked_hero, xp_gained)

    production_gains: dict[str, float] | None = None
    reward_city: models.City | None = None
    loot: dict[str, Any] | None = None
    roll = rng.random()
    if roll < hero_rules.ADVENTURE_ITEM_LOOT_CHANCE:
        hero_service.seed_items(db)
        templates = (
            db.query(models.ItemTemplate)
            .order_by(models.ItemTemplate.name.asc())
            .all()
        )
        if templates:
            template = templates[rng.randrange(len(templates))]
            item = models.HeroItem(
                hero_id=locked_hero.id,
                template_id=template.id,
                is_equipped=False,
            )
            db.add(item)
            db.flush()
            loot = {
                "type": "item",
                "item_id": item.id,
                "name": template.name,
                "rarity": template.rarity,
            }
    elif roll < (
        hero_rules.ADVENTURE_ITEM_LOOT_CHANCE
        + hero_rules.ADVENTURE_RESOURCE_LOOT_CHANCE
    ):
        city = hero_service._ensure_hero_city(db, locked_hero)
        reward_city, production_gains = production.lock_and_recalculate_resources(db, city)
        resource = balance.RESOURCE_FIELDS[rng.randrange(len(balance.RESOURCE_FIELDS))]
        base_amount = rng.randint(
            int(config["resource_min"]), int(config["resource_max"])
        )
        requested = max(
            1,
            int(round(base_amount * (1.0 + bonuses["production"] + bonuses["loot"]))),
        )
        capacity = production.get_storage_limit(reward_city)
        before = float(getattr(reward_city, resource))
        delivered = max(0, min(requested, int(max(capacity - before, 0.0))))
        setattr(reward_city, resource, before + delivered)
        loot = {
            "type": "resource",
            "resource": resource,
            "requested_amount": requested,
            "amount": delivered,
            "storage_capped": delivered < requested,
        }

    result = {
        "rules_version": hero_rules.HERO_RULES_VERSION,
        "seed": adventure.seed,
        "status": "success",
        "damage": damage,
        "xp": xp_gained,
        "loot": loot,
    }
    adventure.result_json = result
    db.add_all([adventure, locked_hero])
    if reward_city is not None:
        db.add(reward_city)
    db.commit()
    if reward_city is not None and production_gains is not None:
        production.record_resource_gains(db, reward_city, production_gains)
    return deepcopy(result)
