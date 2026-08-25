import hashlib
import json
import random
from datetime import timedelta

import pytest

from app import models
from app.routers.auth import create_access_token
from app.services import adventure, hero, hero_rules, production
from app.utils import utc_now


def _join(db, user, city):
    membership = (
        db.query(models.PlayerWorld)
        .filter_by(user_id=user.id, world_id=city.world_id)
        .one_or_none()
    )
    if membership is None:
        db.add(
            models.PlayerWorld(
                user_id=user.id,
                world_id=city.world_id,
                starting_city_id=city.id,
            )
        )
    user.world_id = city.world_id
    db.add(user)
    db.commit()


def _headers(user):
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )
    return {"Authorization": f"Bearer {token}"}


def _resource_seed():
    for index in range(10000):
        seed = hashlib.sha256(f"bm0068-resource-{index}".encode()).hexdigest()
        rng = random.Random(int(seed, 16))
        rng.randint(1, 10)
        roll = rng.random()
        if (
            hero_rules.ADVENTURE_ITEM_LOOT_CHANCE
            <= roll
            < hero_rules.ADVENTURE_ITEM_LOOT_CHANCE
            + hero_rules.ADVENTURE_RESOURCE_LOOT_CHANCE
        ):
            return seed
    raise AssertionError("Could not find deterministic resource seed")


def test_one_independent_hero_per_player_world(db_session, user, city):
    _join(db_session, user, city)
    first = hero.get_hero(db_session, user.id, city.world_id)

    second_world = models.World(name="Hero World 2", is_active=True)
    db_session.add(second_world)
    db_session.flush()
    second_city = models.City(
        name="Second Hero Capital",
        owner_id=user.id,
        world_id=second_world.id,
        x=11,
        y=12,
    )
    db_session.add(second_city)
    db_session.flush()
    db_session.add(
        models.PlayerWorld(
            user_id=user.id,
            world_id=second_world.id,
            starting_city_id=second_city.id,
        )
    )
    db_session.commit()

    second = hero.get_hero(db_session, user.id, second_world.id)
    assert first.id != second.id
    assert first.world_id == city.world_id
    assert second.world_id == second_world.id

    first.level = 2
    db_session.commit()
    hero.distribute_points(db_session, first, 1, 1, 1)
    db_session.refresh(second)
    assert (second.attack_points, second.defense_points, second.production_points) == (0, 0, 0)

    manifest = json.loads(db_session.query(models.World).filter_by(id=city.world_id).one().special_rules)
    assert manifest["hero_package"]["version"] == hero_rules.HERO_RULES_VERSION


def test_attribute_points_reject_negative_values(db_session, user, city):
    _join(db_session, user, city)
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero_obj.level = 2
    db_session.commit()

    with pytest.raises(ValueError, match="cannot be negative"):
        hero.distribute_points(db_session, hero_obj, -1, 0, 0)


def test_equipment_slots_are_exclusive_and_bonuses_are_real(db_session, user, city):
    _join(db_session, user, city)
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero.seed_items(db_session)
    wooden = db_session.query(models.ItemTemplate).filter_by(name="Espada de Madera").one()
    axe = db_session.query(models.ItemTemplate).filter_by(name="Hacha de Guerra").one()
    first_item = models.HeroItem(hero_id=hero_obj.id, template_id=wooden.id)
    second_item = models.HeroItem(hero_id=hero_obj.id, template_id=axe.id)
    db_session.add_all([first_item, second_item])
    db_session.commit()

    hero.equip_item(db_session, hero_obj, first_item.id)
    updated = hero.equip_item(db_session, hero_obj, second_item.id)
    by_id = {item.id: item for item in updated.items}
    assert by_id[first_item.id].is_equipped is False
    assert by_id[second_item.id].is_equipped is True
    assert axe.slot == "weapon"
    assert hero.calculate_total_bonuses(updated)["attack"] == pytest.approx(0.15)


def test_resource_loot_respects_storage_and_retry_is_idempotent(db_session, user, city):
    _join(db_session, user, city)
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    current = next(
        item for item in adventure.get_adventures(db_session, hero_obj) if item.status == "available"
    )

    for resource in ("wood", "stone", "iron", "gold"):
        setattr(city, resource, production.get_storage_limit(city) - 1)
    city.last_production = utc_now()
    current.seed = _resource_seed()
    current.difficulty = "easy"
    current.duration = 1
    current.status = "active"
    current.started_at = utc_now() - timedelta(seconds=5)
    hero_obj.status = "adventure"
    db_session.add_all([city, current, hero_obj])
    db_session.commit()

    result = adventure.claim_adventure(db_session, current.id, hero_obj)
    assert result["status"] == "success"
    assert result["loot"]["type"] == "resource"
    assert result["loot"]["storage_capped"] is True
    assert result["loot"]["amount"] <= 1

    db_session.refresh(city)
    capacity = production.get_storage_limit(city)
    assert all(
        float(getattr(city, resource)) <= capacity
        for resource in ("wood", "stone", "iron", "gold")
    )
    resources_after = tuple(
        float(getattr(city, resource)) for resource in ("wood", "stone", "iron", "gold")
    )
    retry = adventure.claim_adventure(db_session, current.id, hero_obj)
    db_session.refresh(city)
    assert retry == result
    assert tuple(
        float(getattr(city, resource)) for resource in ("wood", "stone", "iron", "gold")
    ) == resources_after


def test_another_hero_cannot_claim_foreign_adventure(db_session, user, city):
    _join(db_session, user, city)
    owner_hero = hero.get_hero(db_session, user.id, city.world_id)
    current = next(
        item for item in adventure.get_adventures(db_session, owner_hero) if item.status == "available"
    )

    intruder = models.User(
        username="hero_intruder",
        email="hero-intruder@example.com",
        hashed_password="placeholder",
        is_verified=True,
        world_id=city.world_id,
    )
    db_session.add(intruder)
    db_session.flush()
    intruder_city = models.City(
        name="Intruder Capital",
        owner_id=intruder.id,
        world_id=city.world_id,
        x=13,
        y=14,
    )
    db_session.add(intruder_city)
    db_session.flush()
    db_session.add(
        models.PlayerWorld(
            user_id=intruder.id,
            world_id=city.world_id,
            starting_city_id=intruder_city.id,
        )
    )
    db_session.commit()
    intruder_hero = hero.get_hero(db_session, intruder.id, city.world_id)

    with pytest.raises(ValueError, match="Not your adventure"):
        adventure.claim_adventure(db_session, current.id, intruder_hero)

    db_session.refresh(current)
    assert current.status == "available"
    assert current.result_json is None


def test_revive_has_server_authoritative_gold_cost(db_session, user, city):
    _join(db_session, user, city)
    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    hero_obj.level = 3
    hero_obj.status = "dead"
    hero_obj.health = 0
    city.gold = 500
    city.last_production = utc_now()
    db_session.add_all([hero_obj, city])
    db_session.commit()

    expected = hero_rules.revive_cost(3)
    revived = hero.revive_hero(db_session, hero_obj)
    db_session.refresh(city)
    assert revived.status == "home"
    assert revived.health == hero_rules.HERO_REVIVE_HEALTH
    assert city.gold == pytest.approx(500 - expected)


def test_hero_api_requires_world_membership(client, db_session, user, city):
    _join(db_session, user, city)
    foreign = models.World(name="Foreign Hero World", is_active=True)
    db_session.add(foreign)
    db_session.commit()

    allowed = client.get(
        "/hero/",
        params={"world_id": city.world_id},
        headers=_headers(user),
    )
    denied = client.get(
        "/hero/",
        params={"world_id": foreign.id},
        headers=_headers(user),
    )
    balance_response = client.get("/economy/balance_preview")

    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["world_id"] == city.world_id
    assert denied.status_code == 403
    assert balance_response.status_code == 200
    assert balance_response.json()["hero_package"]["rules_version"] == hero_rules.HERO_RULES_VERSION
