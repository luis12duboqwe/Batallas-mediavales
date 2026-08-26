import pytest

from app import models
from app.services import hero, hero_rules


def _second_world_city(db_session, user):
    world = models.World(name="HeroSecondWorld", speed_modifier=1.0, resource_modifier=1.0)
    db_session.add(world)
    db_session.flush()
    city = models.City(
        name="Second Hero Capital",
        owner_id=user.id,
        world_id=world.id,
        x=21,
        y=22,
    )
    db_session.add(city)
    db_session.commit()
    db_session.refresh(world)
    db_session.refresh(city)
    return world, city


def test_hero_is_isolated_per_world(db_session, user, city):
    second_world, second_city = _second_world_city(db_session, user)

    first = hero.get_hero(db_session, user.id, city.world_id)
    second = hero.get_hero(db_session, user.id, second_world.id)

    assert first.id != second.id
    assert first.world_id == city.world_id
    assert first.city_id == city.id
    assert second.world_id == second_world.id
    assert second.city_id == second_city.id
    assert db_session.query(models.Hero).filter_by(user_id=user.id).count() == 2


def test_distribute_points_rejects_negative_and_overspend(db_session, user, city):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero_obj.level = 2
    db_session.commit()

    with pytest.raises(ValueError, match="cannot be negative"):
        hero.distribute_points(db_session, hero_obj, -1, 0, 0)

    with pytest.raises(ValueError, match="Not enough points"):
        hero.distribute_points(db_session, hero_obj, 5, 0, 0)

    updated = hero.distribute_points(db_session, hero_obj, 2, 1, 1)
    assert updated.attack_points == 2
    assert updated.defense_points == 1
    assert updated.production_points == 1
    assert hero.get_available_points(updated) == 0


def test_revive_charges_gold_once_and_restores_configured_health(db_session, user, city):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    city.gold = 500.0
    hero_obj.status = "dead"
    hero_obj.health = 0.0
    db_session.commit()

    revived = hero.revive_hero(db_session, hero_obj)
    db_session.refresh(city)
    assert revived.status == "home"
    assert revived.health == hero_rules.HERO_REVIVE_HEALTH
    assert city.gold == pytest.approx(500.0 - hero_rules.HERO_REVIVE_COST_GOLD, abs=0.1)

    with pytest.raises(ValueError, match="not dead"):
        hero.revive_hero(db_session, revived)
    db_session.refresh(city)
    assert city.gold == pytest.approx(500.0 - hero_rules.HERO_REVIVE_COST_GOLD, abs=0.1)


def test_equipment_enforces_ownership_and_one_item_per_slot(db_session, user, city):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero.seed_items(db_session)
    templates = {
        row.name: row for row in db_session.query(models.ItemTemplate).all()
    }
    first_weapon = models.HeroItem(
        hero_id=hero_obj.id,
        template_id=templates["Espada de Madera"].id,
    )
    second_weapon = models.HeroItem(
        hero_id=hero_obj.id,
        template_id=templates["Hacha de Guerra"].id,
    )
    db_session.add_all([first_weapon, second_weapon])
    db_session.commit()

    hero.equip_item(db_session, hero_obj, first_weapon.id)
    hero.equip_item(db_session, hero_obj, second_weapon.id)
    db_session.refresh(first_weapon)
    db_session.refresh(second_weapon)
    assert first_weapon.is_equipped is False
    assert second_weapon.is_equipped is True

    other_user = models.User(
        username="hero_other",
        email="hero_other@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(other_user)
    db_session.flush()
    other_city = models.City(
        name="Other Hero City",
        owner_id=other_user.id,
        world_id=city.world_id,
        x=31,
        y=32,
    )
    db_session.add(other_city)
    db_session.commit()
    other_hero = hero.get_hero(db_session, other_user.id, city.world_id)

    with pytest.raises(ValueError, match="not found in inventory"):
        hero.equip_item(db_session, other_hero, second_weapon.id)
