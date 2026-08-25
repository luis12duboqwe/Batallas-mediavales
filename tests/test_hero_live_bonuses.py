from datetime import timedelta

import pytest

from app import models
from app.services import balance, combat, hero, hero_rules, movement, production
from app.services import event as event_service
from app.utils import utc_now


def _equip(db_session, hero_obj: models.Hero, name: str) -> models.HeroItem:
    hero.seed_items(db_session)
    template = db_session.query(models.ItemTemplate).filter_by(name=name).one()
    item = models.HeroItem(hero_id=hero_obj.id, template_id=template.id)
    db_session.add(item)
    db_session.commit()
    hero.equip_item(db_session, hero_obj, item.id)
    db_session.expire(hero_obj, ["items"])
    return item


def test_attack_and_defense_items_modify_live_combat_with_versioned_caps(
    db_session,
    user,
    city,
):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero_obj.attack_points = 2
    hero_obj.defense_points = 2
    hero_obj.status = "home"
    db_session.commit()
    _equip(db_session, hero_obj, "Hacha de Guerra")
    hero_obj.status = "moving"
    db_session.commit()
    db_session.expire(hero_obj, ["items"])

    troops = {"basic_infantry": 10}
    base_distribution, base_attack = combat._split_attack_by_type(troops, None)
    boosted_distribution, boosted_attack = combat._split_attack_by_type(troops, hero_obj)
    expected_attack_bonus = 0.02 + 0.15

    assert hero_rules.attack_bonus(hero_obj) == pytest.approx(expected_attack_bonus)
    assert boosted_attack == pytest.approx(base_attack * (1 + expected_attack_bonus))
    for category in base_distribution:
        assert boosted_distribution[category] == pytest.approx(
            base_distribution[category] * (1 + expected_attack_bonus)
        )

    hero_obj.status = "home"
    db_session.commit()
    _equip(db_session, hero_obj, "Armadura de Placas")
    db_session.expire(hero_obj, ["items"])
    base_defense = combat._defense_values(troops, None)
    boosted_defense = combat._defense_values(troops, hero_obj)
    expected_defense_bonus = 0.02 + 0.20

    assert hero_rules.defense_bonus(hero_obj) == pytest.approx(expected_defense_bonus)
    for category in base_defense:
        assert boosted_defense[category] == pytest.approx(
            base_defense[category] * (1 + expected_defense_bonus)
        )

    assert hero_rules.HERO_RULES_VERSION == "2026.08.25-bm0068-v1"


def test_hero_bonus_caps_prevent_item_or_attribute_stacking_abuse(
    db_session,
    user,
    city,
):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero_obj.attack_points = 999
    hero_obj.defense_points = 999
    db_session.commit()
    _equip(db_session, hero_obj, "Hacha de Guerra")
    _equip(db_session, hero_obj, "Caballo de Guerra")
    _equip(db_session, hero_obj, "Mapa Antiguo")
    db_session.expire(hero_obj, ["items"])

    assert hero_rules.attack_bonus(hero_obj) == hero_rules.HERO_MAX_ATTACK_BONUS
    assert hero_rules.defense_bonus(hero_obj) == hero_rules.HERO_MAX_DEFENSE_BONUS
    assert hero_rules.speed_bonus(hero_obj) == hero_rules.HERO_MAX_SPEED_BONUS


def test_production_attribute_affects_only_home_alive_hero_city(
    db_session,
    user,
    city,
):
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero_obj.production_points = 4
    hero_obj.status = "home"
    hero_obj.health = 100
    db_session.commit()

    home_rates = production.get_gross_production_per_hour(db_session, city)
    expected_bonus = 4 * hero_rules.HERO_PRODUCTION_BONUS_PER_POINT
    for resource in balance.RESOURCE_FIELDS:
        assert home_rates[resource] == pytest.approx(
            balance.PRODUCTION_RATES_PER_HOUR[resource] * (1 + expected_bonus)
        )

    hero_obj.status = "moving"
    db_session.commit()
    away_rates = production.get_gross_production_per_hour(db_session, city)
    for resource in balance.RESOURCE_FIELDS:
        assert away_rates[resource] == pytest.approx(
            balance.PRODUCTION_RATES_PER_HOUR[resource]
        )


def test_speed_item_is_frozen_into_march_and_hero_returns_home(
    db_session,
    user,
    city,
    monkeypatch,
):
    monkeypatch.setattr(movement.anticheat, "check_action_speed", lambda *args, **kwargs: None)
    monkeypatch.setattr(movement.anticheat, "check_movement_legitimacy", lambda *args, **kwargs: None)
    monkeypatch.setattr(movement, "_run_dispatch_side_effects", lambda *args, **kwargs: None)

    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    _equip(db_session, hero_obj, "Caballo de Guerra")
    db_session.expire(hero_obj, ["items"])
    speed_bonus = hero_rules.speed_bonus(hero_obj)
    assert speed_bonus == pytest.approx(0.25)

    troop = models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=6)
    target = models.City(
        name="Hero Speed Target",
        owner_id=None,
        world_id=city.world_id,
        x=city.x + 4,
        y=city.y + 3,
        wood=0,
        stone=0,
        iron=0,
        gold=0,
        last_production=utc_now(),
    )
    db_session.add_all([troop, target])
    db_session.commit()
    db_session.refresh(target)

    modifiers = event_service.get_active_modifiers(db_session, world_id=city.world_id)
    expected_speed = (
        balance.UNIT_SPEED["basic_infantry"]
        * float(modifiers.get("movement_speed", 1.0))
        * float(city.world.speed_modifier)
        * (1 + speed_bonus)
    )

    march = movement.send_movement(
        db_session,
        city,
        target.id,
        "attack",
        troops={"basic_infantry": 2},
        target_city=target,
        hero_id=hero_obj.id,
    )
    assert march.speed_used == pytest.approx(expected_speed)
    db_session.refresh(hero_obj)
    assert hero_obj.status == "moving"

    hero.seed_items(db_session)
    map_template = db_session.query(models.ItemTemplate).filter_by(name="Mapa Antiguo").one()
    map_item = models.HeroItem(hero_id=hero_obj.id, template_id=map_template.id)
    db_session.add(map_item)
    db_session.commit()
    with pytest.raises(ValueError, match="only change while hero is home"):
        hero.equip_item(db_session, hero_obj, map_item.id)

    with pytest.raises(ValueError, match="Hero is busy"):
        movement.send_movement(
            db_session,
            city,
            target.id,
            "attack",
            troops={"basic_infantry": 1},
            target_city=target,
            hero_id=hero_obj.id,
        )

    march.arrival_time = utc_now() - timedelta(seconds=1)
    db_session.add(march)
    db_session.commit()
    processed = movement.resolve_due_movements(db_session)
    assert [entry.id for entry in processed] == [march.id]

    return_move = (
        db_session.query(models.Movement)
        .filter_by(
            movement_type="return",
            hero_id=hero_obj.id,
            world_id=city.world_id,
            status="ongoing",
        )
        .one()
    )
    assert return_move.speed_used == pytest.approx(expected_speed)
    db_session.refresh(hero_obj)
    assert hero_obj.status == "moving"

    return_move.arrival_time = utc_now() - timedelta(seconds=1)
    db_session.add(return_move)
    db_session.commit()
    movement.resolve_due_movements(db_session)
    db_session.refresh(hero_obj)
    assert hero_obj.status == "home"


def test_cross_world_hero_cannot_be_assigned_to_movement(
    db_session,
    user,
    city,
    monkeypatch,
):
    monkeypatch.setattr(movement.anticheat, "check_action_speed", lambda *args, **kwargs: None)
    monkeypatch.setattr(movement, "_run_dispatch_side_effects", lambda *args, **kwargs: None)

    second_world = models.World(name="Foreign Hero World", speed_modifier=1.0, resource_modifier=1.0)
    db_session.add(second_world)
    db_session.flush()
    second_city = models.City(
        name="Foreign Hero Capital",
        owner_id=user.id,
        world_id=second_world.id,
        x=40,
        y=41,
    )
    target = models.City(
        name="Local Hero Target",
        owner_id=None,
        world_id=city.world_id,
        x=city.x + 2,
        y=city.y + 2,
    )
    troop = models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=2)
    db_session.add_all([second_city, target, troop])
    db_session.commit()
    foreign_hero = hero.get_hero(db_session, user.id, second_world.id)

    with pytest.raises(ValueError, match="does not belong to the origin city and world"):
        movement.send_movement(
            db_session,
            city,
            target.id,
            "attack",
            troops={"basic_infantry": 1},
            target_city=target,
            hero_id=foreign_hero.id,
        )

    db_session.refresh(troop)
    assert troop.quantity == 2
    assert db_session.query(models.Movement).filter_by(hero_id=foreign_hero.id).count() == 0
