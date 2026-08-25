"""Server-authoritative hero lifecycle for the BM-0068 package."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from .. import models
from . import hero_rules, production

XP_TABLE = [0] + [
    int(100 * (1.2 ** (i - 1))) for i in range(1, hero_rules.HERO_LEVEL_CAP + 1)
]


def seed_items(db: Session) -> None:
    """Idempotently normalize the legacy item templates to the canonical catalog."""

    changed = False
    for definition in hero_rules.ITEM_CATALOG.values():
        template = (
            db.query(models.ItemTemplate)
            .filter(models.ItemTemplate.name == definition["name"])
            .one_or_none()
        )
        if template is None:
            template = models.ItemTemplate(name=definition["name"])
            db.add(template)
            changed = True
        for field in ("description", "slot", "rarity", "bonus_type", "bonus_value"):
            expected = definition[field]
            if getattr(template, field, None) != expected:
                setattr(template, field, expected)
                changed = True
    if changed:
        db.commit()


def _world_for_update(db: Session, world_id: int) -> models.World:
    world = (
        db.query(models.World)
        .filter(models.World.id == world_id)
        .with_for_update()
        .one_or_none()
    )
    if world is None:
        raise ValueError("World not found")
    return world


def _require_membership(db: Session, user_id: int, world_id: int) -> None:
    membership = (
        db.query(models.PlayerWorld.id)
        .filter(
            models.PlayerWorld.user_id == user_id,
            models.PlayerWorld.world_id == world_id,
        )
        .first()
    )
    if membership is None:
        raise ValueError("Player has not joined this world")


def get_hero(db: Session, user_id: int, world_id: int) -> models.Hero:
    """Return/create exactly one hero for this player in this joined world."""

    _require_membership(db, user_id, world_id)
    world = _world_for_update(db, world_id)
    manifest_changed = hero_rules.pin_world_rules(world)
    seed_items(db)

    hero = (
        db.query(models.Hero)
        .options(selectinload(models.Hero.items).selectinload(models.HeroItem.template))
        .filter(
            models.Hero.user_id == user_id,
            models.Hero.world_id == world_id,
        )
        .one_or_none()
    )
    created = False
    if hero is None:
        city = (
            db.query(models.City)
            .filter(
                models.City.owner_id == user_id,
                models.City.world_id == world_id,
            )
            .order_by(models.City.id.asc())
            .first()
        )
        hero = models.Hero(
            user_id=user_id,
            world_id=world_id,
            city_id=city.id if city else None,
            health=hero_rules.HERO_MAX_HEALTH,
            status="home",
        )
        db.add(hero)
        created = True

    if manifest_changed or created:
        db.commit()
        db.refresh(hero)
    return hero


def lock_hero_for_update(db: Session, hero_id: int) -> models.Hero:
    hero = (
        db.query(models.Hero)
        .options(selectinload(models.Hero.items).selectinload(models.HeroItem.template))
        .filter(models.Hero.id == hero_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if hero is None:
        raise ValueError("Hero not found")
    return hero


def add_xp(hero: models.Hero, xp_amount: int) -> int:
    """Apply XP without committing; the enclosing domain transaction owns commit."""

    remaining = max(int(xp_amount), 0)
    hero.xp += remaining
    levels_gained = 0
    while hero.level < hero_rules.HERO_LEVEL_CAP:
        threshold = XP_TABLE[hero.level]
        if hero.xp < threshold:
            break
        hero.xp -= threshold
        hero.level += 1
        levels_gained += 1
    return levels_gained


def get_available_points(hero: models.Hero) -> int:
    total_points = max(hero.level - 1, 0) * hero_rules.HERO_POINTS_PER_LEVEL
    used_points = max(hero.attack_points, 0) + max(hero.defense_points, 0) + max(
        hero.production_points, 0
    )
    return max(0, total_points - used_points)


def distribute_points(
    db: Session,
    hero: models.Hero,
    attack: int,
    defense: int,
    production_points: int,
) -> models.Hero:
    values = (int(attack), int(defense), int(production_points))
    if any(value < 0 for value in values):
        raise ValueError("Attribute points cannot be negative")

    locked = lock_hero_for_update(db, hero.id)
    cost = sum(values)
    if cost <= 0:
        return locked
    if cost > get_available_points(locked):
        raise ValueError("Not enough points available")

    locked.attack_points += values[0]
    locked.defense_points += values[1]
    locked.production_points += values[2]
    db.add(locked)
    db.commit()
    db.refresh(locked)
    return locked


def _ensure_hero_city(db: Session, hero: models.Hero) -> models.City:
    if hero.city_id is not None:
        city = (
            db.query(models.City)
            .filter(
                models.City.id == hero.city_id,
                models.City.owner_id == hero.user_id,
                models.City.world_id == hero.world_id,
            )
            .one_or_none()
        )
        if city is not None:
            return city
    city = (
        db.query(models.City)
        .filter(
            models.City.owner_id == hero.user_id,
            models.City.world_id == hero.world_id,
        )
        .order_by(models.City.id.asc())
        .first()
    )
    if city is None:
        raise ValueError("Hero has no city in this world")
    hero.city_id = city.id
    return city


def revive_cost(hero: models.Hero) -> dict[str, float]:
    return {
        hero_rules.HERO_REVIVE_RESOURCE: float(hero_rules.revive_cost(hero.level))
    }


def revive_hero(db: Session, hero: models.Hero) -> models.Hero:
    locked = lock_hero_for_update(db, hero.id)
    if locked.status != "dead":
        raise ValueError("Hero is not dead")

    city = _ensure_hero_city(db, locked)
    locked_city, production_gains = production.lock_and_recalculate_resources(db, city)
    cost = revive_cost(locked)
    production.pay_cost(locked_city, cost)
    locked.status = "home"
    locked.health = hero_rules.HERO_REVIVE_HEALTH
    db.add_all([locked, locked_city])
    db.commit()
    db.refresh(locked)
    production.record_resource_gains(db, locked_city, production_gains)
    return locked


def calculate_total_bonuses(hero: models.Hero) -> dict[str, float]:
    """Return package bonuses with explicit, bounded adventure semantics."""

    bonuses = {
        "attack": max(hero.attack_points, 0)
        * hero_rules.ATTRIBUTE_EFFECTS["attack"]["per_point"],
        "defense": max(hero.defense_points, 0)
        * hero_rules.ATTRIBUTE_EFFECTS["defense"]["per_point"],
        "production": max(hero.production_points, 0)
        * hero_rules.ATTRIBUTE_EFFECTS["production"]["per_point"],
        "speed": 0.0,
        "loot": 0.0,
    }
    for item in hero.items:
        if not item.is_equipped or item.template is None:
            continue
        bonus_type = str(item.template.bonus_type)
        if bonus_type in bonuses:
            bonuses[bonus_type] += max(float(item.template.bonus_value), 0.0)

    bonuses["defense"] = min(
        bonuses["defense"], hero_rules.HERO_MAX_DEFENSE_REDUCTION
    )
    bonuses["speed"] = min(bonuses["speed"], hero_rules.HERO_MAX_SPEED_REDUCTION)
    return bonuses


def equip_item(db: Session, hero: models.Hero, item_id: int) -> models.Hero:
    locked = lock_hero_for_update(db, hero.id)
    item = next((candidate for candidate in locked.items if candidate.id == item_id), None)
    if item is None:
        raise ValueError("Item not found in inventory")
    if item.template is None:
        raise ValueError("Item template is missing")

    for current in locked.items:
        if (
            current.id != item.id
            and current.is_equipped
            and current.template is not None
            and current.template.slot == item.template.slot
        ):
            current.is_equipped = False
    item.is_equipped = True
    db.commit()
    return lock_hero_for_update(db, locked.id)


def unequip_item(db: Session, hero: models.Hero, item_id: int) -> models.Hero:
    locked = lock_hero_for_update(db, hero.id)
    item = next((candidate for candidate in locked.items if candidate.id == item_id), None)
    if item is None:
        raise ValueError("Item not found in inventory")
    item.is_equipped = False
    db.commit()
    return lock_hero_for_update(db, locked.id)


def item_payload(item: models.HeroItem) -> dict[str, Any]:
    template = item.template
    return {
        "id": item.id,
        "hero_id": item.hero_id,
        "template_id": item.template_id,
        "is_equipped": bool(item.is_equipped),
        "name": template.name,
        "description": template.description,
        "slot": template.slot,
        "rarity": template.rarity,
        "bonus_type": template.bonus_type,
        "bonus_value": float(template.bonus_value),
    }
