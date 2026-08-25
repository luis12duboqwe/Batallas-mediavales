from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models
from . import hero_rules, production

# Compatibility alias consumed by combat/movement code.
XP_TABLE = hero_rules.HERO_XP_TABLE


def _resolve_world_id(db: Session, user_id: int, world_id: int | None) -> int:
    if world_id is not None:
        return int(world_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user and user.world_id is not None:
        return int(user.world_id)
    membership = (
        db.query(models.PlayerWorld)
        .filter(models.PlayerWorld.user_id == user_id)
        .order_by(models.PlayerWorld.world_id.asc())
        .first()
    )
    if membership:
        return int(membership.world_id)
    city = (
        db.query(models.City)
        .filter(models.City.owner_id == user_id)
        .order_by(models.City.id.asc())
        .first()
    )
    if city:
        return int(city.world_id)
    raise ValueError("User is not a member of any world")


def get_hero(db: Session, user_id: int, world_id: int | None = None) -> models.Hero:
    """Return/create exactly one hero for a user inside one world."""

    resolved_world_id = _resolve_world_id(db, user_id, world_id)
    # Serialize first creation per account so concurrent GETs cannot race the
    # (user_id, world_id) unique constraint.
    db.query(models.User).filter(models.User.id == user_id).with_for_update().one()
    hero = (
        db.query(models.Hero)
        .filter(
            models.Hero.user_id == user_id,
            models.Hero.world_id == resolved_world_id,
        )
        .one_or_none()
    )
    if hero:
        return hero

    city = (
        db.query(models.City)
        .filter(
            models.City.owner_id == user_id,
            models.City.world_id == resolved_world_id,
        )
        .order_by(models.City.id.asc())
        .first()
    )
    if city is None:
        db.rollback()
        raise ValueError("Hero requires an owned city in this world")

    hero = models.Hero(
        user_id=user_id,
        world_id=resolved_world_id,
        city_id=city.id,
        health=hero_rules.HERO_MAX_HEALTH,
        status="home",
    )
    db.add(hero)
    db.commit()
    db.refresh(hero)
    return hero


def add_xp(
    db: Session,
    hero: models.Hero,
    xp_amount: int,
    *,
    commit: bool = True,
) -> models.Hero:
    amount = int(xp_amount)
    if amount < 0:
        raise ValueError("XP amount cannot be negative")
    hero.xp += amount
    while hero.level < hero_rules.HERO_MAX_LEVEL and hero.xp >= XP_TABLE[hero.level]:
        hero.xp -= XP_TABLE[hero.level]
        hero.level += 1
    db.add(hero)
    if commit:
        db.commit()
        db.refresh(hero)
    return hero


def get_available_points(hero: models.Hero) -> int:
    total_points = (hero.level - 1) * hero_rules.HERO_ATTRIBUTE_POINTS_PER_LEVEL
    used_points = hero.attack_points + hero.defense_points + hero.production_points
    return max(0, total_points - used_points)


def distribute_points(
    db: Session,
    hero: models.Hero,
    attack: int,
    defense: int,
    production_points: int,
) -> models.Hero:
    values = [int(attack), int(defense), int(production_points)]
    if any(value < 0 for value in values):
        raise ValueError("Attribute points cannot be negative")

    locked = (
        db.query(models.Hero)
        .filter(models.Hero.id == hero.id, models.Hero.world_id == hero.world_id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    cost = sum(values)
    if cost > get_available_points(locked):
        db.rollback()
        raise ValueError("Not enough points available")

    locked.attack_points += values[0]
    locked.defense_points += values[1]
    locked.production_points += values[2]
    db.commit()
    db.refresh(locked)
    return locked


def revive_hero(db: Session, hero: models.Hero) -> models.Hero:
    """Revive atomically and charge the hero city's gold."""

    locked = (
        db.query(models.Hero)
        .filter(models.Hero.id == hero.id, models.Hero.world_id == hero.world_id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    if locked.status != "dead":
        db.rollback()
        raise ValueError("Hero is not dead")
    if locked.city_id is None:
        db.rollback()
        raise ValueError("Hero has no home city")

    city = (
        db.query(models.City)
        .filter(
            models.City.id == locked.city_id,
            models.City.world_id == locked.world_id,
            models.City.owner_id == locked.user_id,
        )
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if city is None:
        db.rollback()
        raise ValueError("Hero home city is invalid")

    city, gains = production.recalculate_resources(
        db,
        city,
        return_gains=True,
        commit=False,
    )
    cost = {"gold": hero_rules.HERO_REVIVE_COST_GOLD}
    if not production.check_cost(city, cost):
        db.rollback()
        raise ValueError("Insufficient gold to revive hero")
    production.pay_cost(city, cost)
    locked.status = "home"
    locked.health = hero_rules.HERO_REVIVE_HEALTH
    db.add_all([city, locked])
    db.commit()
    db.refresh(locked)
    production.record_resource_gains(db, city, gains)
    return locked


def calculate_total_bonuses(hero: models.Hero) -> dict[str, float]:
    bonuses = {
        "attack": hero_rules.attack_bonus(hero),
        "defense": hero_rules.defense_bonus(hero),
        "production": hero_rules.production_bonus(hero),
        "attack_infantry": 0.0,
        "attack_cavalry": 0.0,
        "defense_infantry": 0.0,
        "defense_cavalry": 0.0,
        "speed": hero_rules.speed_bonus(hero),
    }
    for item in hero.items:
        if not item.is_equipped:
            continue
        template = item.template
        if template.bonus_type in {
            "attack_infantry",
            "attack_cavalry",
            "defense_infantry",
            "defense_cavalry",
        }:
            bonuses[template.bonus_type] += template.bonus_value
        elif template.bonus_type == "attack_all":
            bonuses["attack_infantry"] += template.bonus_value
            bonuses["attack_cavalry"] += template.bonus_value
    return bonuses


def _require_home_loadout(locked: models.Hero) -> None:
    if locked.status != "home":
        raise ValueError("Hero equipment can only change while hero is home")
    if float(locked.health) <= 0:
        raise ValueError("Dead hero cannot change equipment")


def equip_item(db: Session, hero: models.Hero, item_id: int) -> models.Hero:
    locked = (
        db.query(models.Hero)
        .filter(models.Hero.id == hero.id, models.Hero.world_id == hero.world_id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    try:
        _require_home_loadout(locked)
    except ValueError:
        db.rollback()
        raise

    item = (
        db.query(models.HeroItem)
        .filter(models.HeroItem.id == item_id, models.HeroItem.hero_id == locked.id)
        .with_for_update()
        .one_or_none()
    )
    if item is None:
        db.rollback()
        raise ValueError("Item not found in inventory")
    template = item.template
    if template.slot not in hero_rules.HERO_EQUIPMENT_SLOTS:
        db.rollback()
        raise ValueError("Invalid equipment slot")

    current_items = (
        db.query(models.HeroItem)
        .join(models.ItemTemplate)
        .filter(
            models.HeroItem.hero_id == locked.id,
            models.HeroItem.is_equipped.is_(True),
            models.ItemTemplate.slot == template.slot,
        )
        .with_for_update()
        .all()
    )
    for current in current_items:
        current.is_equipped = False
    item.is_equipped = True
    db.commit()
    db.refresh(locked)
    return locked


def unequip_item(db: Session, hero: models.Hero, item_id: int) -> models.Hero:
    locked = (
        db.query(models.Hero)
        .filter(models.Hero.id == hero.id, models.Hero.world_id == hero.world_id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    try:
        _require_home_loadout(locked)
    except ValueError:
        db.rollback()
        raise

    item = (
        db.query(models.HeroItem)
        .filter(models.HeroItem.id == item_id, models.HeroItem.hero_id == locked.id)
        .with_for_update()
        .one_or_none()
    )
    if item is None:
        db.rollback()
        raise ValueError("Item not found in inventory")
    item.is_equipped = False
    db.commit()
    db.refresh(locked)
    return locked


def seed_items(db: Session) -> None:
    """Idempotently align item templates with the canonical BM-0068 catalog."""

    by_name = {row.name: row for row in db.query(models.ItemTemplate).all()}
    for definition in hero_rules.HERO_ITEM_CATALOG:
        item = by_name.get(definition["name"])
        if item is None:
            item = models.ItemTemplate(name=definition["name"])
            db.add(item)
        item.description = definition["description"]
        item.slot = definition["slot"]
        item.rarity = definition["rarity"]
        item.bonus_type = definition["bonus_type"]
        item.bonus_value = definition["bonus_value"]
    db.commit()
