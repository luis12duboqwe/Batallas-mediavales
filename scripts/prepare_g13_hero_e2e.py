"""Prepare one deterministic BM-0068 hero/item/adventure Browser G13 fixture."""

from __future__ import annotations

from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import hero as hero_service
from app.services import hero_rules, tutorial, world_membership
from app.utils import utc_now


USERNAME = "g13_hero"
PASSWORD = "G13-Hero-Test-2026!"
EMAIL = "g13-hero@example.com"


def _get_or_create_user(db) -> models.User:
    user = db.query(models.User).filter_by(username=USERNAME).one_or_none()
    if user is None:
        user = models.User(
            username=USERNAME,
            email=EMAIL,
            hashed_password=get_password_hash(PASSWORD),
            is_verified=True,
            protection_ends_at=utc_now() - timedelta(hours=1),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email = EMAIL
        user.hashed_password = get_password_hash(PASSWORD)
        user.is_verified = True
        user.protection_ends_at = utc_now() - timedelta(hours=1)
        db.add(user)
        db.commit()
    return user


def main() -> None:
    db = SessionLocal()
    try:
        world = (
            db.query(models.World)
            .filter(models.World.is_active.is_(True))
            .order_by(models.World.id.asc())
            .first()
        )
        if world is None:
            raise RuntimeError("Canonical seed did not create an active world")

        user = _get_or_create_user(db)
        world_membership.join_world(db, user, world.id)
        membership = (
            db.query(models.PlayerWorld)
            .filter_by(user_id=user.id, world_id=world.id)
            .one()
        )
        city = (
            db.query(models.City)
            .filter_by(id=membership.starting_city_id, owner_id=user.id, world_id=world.id)
            .one()
        )
        user.tutorial_step = tutorial.FINAL_STEP
        user.tutorial_reward_claimed = True
        user.world_id = world.id
        city.wood = city.stone = city.iron = city.gold = 1000.0
        city.last_production = utc_now()
        db.add_all([user, city])
        db.commit()

        hero_service.seed_items(db)
        hero = hero_service.get_hero(db, user.id, world.id)

        # Idempotent reruns: keep one canonical hero but reset the BM-0068
        # browser-owned inventory/adventures to a known pre-journey state.
        db.query(models.Adventure).filter_by(hero_id=hero.id).delete(
            synchronize_session=False
        )
        db.query(models.HeroItem).filter_by(hero_id=hero.id).delete(
            synchronize_session=False
        )
        hero.name = "Comandante G13"
        hero.level = 2
        hero.xp = 0
        hero.health = hero_rules.HERO_MAX_HEALTH
        hero.status = "home"
        hero.attack_points = 0
        hero.defense_points = 0
        hero.production_points = 0
        hero.city_id = city.id
        db.add(hero)
        db.flush()

        template = (
            db.query(models.ItemTemplate)
            .filter_by(name="Espada de Madera")
            .one()
        )
        item = models.HeroItem(
            hero_id=hero.id,
            template_id=template.id,
            is_equipped=False,
        )
        # Duration zero is intentional: the browser still executes the real
        # start endpoint (which persists its SHA-256 outcome seed), then the
        # real claim endpoint becomes immediately eligible without sleeps.
        adventure = models.Adventure(
            hero_id=hero.id,
            difficulty="easy",
            duration=0,
            status="available",
            rules_version=hero_rules.HERO_RULES_VERSION,
        )
        db.add_all([item, adventure])
        db.commit()
        db.refresh(item)
        db.refresh(adventure)

        if hero.world_id != world.id or hero.city_id != city.id:
            raise RuntimeError("G13 hero is not scoped to the active world/city")
        if hero_service.get_available_points(hero) != hero_rules.HERO_ATTRIBUTE_POINTS_PER_LEVEL:
            raise RuntimeError("G13 level-2 hero does not expose four attribute points")
        if item.template.slot != "weapon" or item.is_equipped:
            raise RuntimeError("G13 inventory item precondition mismatch")
        if adventure.status != "available" or adventure.duration != 0:
            raise RuntimeError("G13 adventure precondition mismatch")

        print(
            "prepared-g13:"
            f"{user.id}:{world.id}:{city.id}:hero={hero.id}:"
            f"item={item.id}:adventure={adventure.id}:"
            f"rules={hero_rules.HERO_RULES_VERSION}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
