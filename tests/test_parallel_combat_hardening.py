"""Adversarial service-boundary tests owned by the parallel combat branch."""

import json

import pytest

from app import models
from app.services import balance, combat, production


def _other_world(db_session):
    world = models.World(name="Combat other world", is_active=True)
    db_session.add(world)
    db_session.flush()
    return world


def test_parallel_combat_rejects_cross_world_city_without_mutation(
    db_session, city, second_city
):
    other_world = _other_world(db_session)
    second_city.world_id = other_world.id
    second_city.wood = 600.0
    db_session.commit()
    original = (city.wood, second_city.wood, second_city.owner_id, second_city.loyalty)

    with pytest.raises(ValueError, match="world"):
        combat.resolve_battle(
            city, second_city, {"noble": 5, "basic_infantry": 50}, seed="cross-world"
        )

    assert (city.wood, second_city.wood, second_city.owner_id, second_city.loyalty) == original


def test_parallel_combat_rejects_cross_world_oasis_before_reward(
    db_session, city
):
    other_world = _other_world(db_session)
    oasis = models.Oasis(
        world_id=other_world.id,
        x=9,
        y=9,
        resource_type="wood",
        bonus_percent=25,
        troops={},
    )
    db_session.add(oasis)
    db_session.commit()
    before = {key: getattr(city, key) for key in balance.RESOURCE_FIELDS}

    with pytest.raises(ValueError, match="world"):
        combat.resolve_oasis_battle(city, oasis, {"basic_infantry": 10})

    assert {key: getattr(city, key) for key in balance.RESOURCE_FIELDS} == before
    assert oasis.owner_city_id is None


def test_parallel_combat_rejects_self_target_without_side_effects(city):
    before = {key: getattr(city, key) for key in balance.RESOURCE_FIELDS}
    with pytest.raises(ValueError, match="itself|same city"):
        combat.resolve_battle(city, city, {"noble": 2})
    assert {key: getattr(city, key) for key in balance.RESOURCE_FIELDS} == before


@pytest.mark.parametrize(
    "attacking_troops",
    [
        {"basic_infantry": -1},
        {"invalid_unit_from_client": 3},
        {"archer": 1.5},
        {"archer": True},
    ],
)
def test_parallel_combat_rejects_invalid_armies(city, second_city, attacking_troops):
    with pytest.raises(ValueError, match="troop|unit|amount|quantity"):
        combat.resolve_battle(city, second_city, attacking_troops)


def test_parallel_combat_rejects_foreign_world_hero(
    db_session, city, user, second_city
):
    other_world = _other_world(db_session)
    foreign_hero = models.Hero(
        user_id=user.id,
        world_id=other_world.id,
        city_id=city.id,
        status="moving",
        health=100,
    )
    db_session.add(foreign_hero)
    db_session.commit()

    with pytest.raises(ValueError, match="hero|world"):
        combat.resolve_battle(
            city, second_city, {"basic_infantry": 10},
            attacker_hero=foreign_hero,
            seed="foreign-hero",
        )
    assert foreign_hero.health == 100


def test_parallel_combat_pvp_nobles_never_conquer_player(
    db_session, city, second_city
):
    second_city.loyalty = 1
    second_city.wood = 500.0
    initial_owner = second_city.owner_id

    outcome = combat.resolve_battle(
        city, second_city, {"noble": 100}, seed="pvp-no-conquest"
    )

    assert outcome["outcome"] == "attacker_victory"
    assert outcome["conquest"] is False
    assert outcome["loyalty_change"] == 0
    assert second_city.owner_id == initial_owner
    assert second_city.loyalty == 1
    assert all(value >= 0 for value in outcome["loot"].values())
    report = json.loads(combat.build_battle_report_content(city, second_city, outcome))
    assert report["conquest"] is False


def test_parallel_combat_oasis_reward_report_matches_fractional_storage_capacity(
    db_session, city, monkeypatch
):
    oasis = models.Oasis(
        world_id=city.world_id,
        x=12,
        y=12,
        resource_type="wood",
        bonus_percent=25,
        troops={},
    )
    db_session.add(oasis)
    db_session.commit()
    storage_limit = float(production.get_storage_limit(city))
    city.wood = storage_limit - 0.25
    before = float(city.wood)
    monkeypatch.setattr(
        combat._impl,
        "resolve_oasis_battle",
        lambda *args, **kwargs: {"conquered": True, "conquest": True, "loot": {}},
    )

    result = combat.resolve_oasis_battle(city, oasis)

    assert result["pve"]["reward_eligible"] is True
    assert result["loot"].get("wood", 0) == 0
    assert result["pve"]["credited_reward"] == result["loot"]
    assert city.wood == before


def test_parallel_combat_rejects_foreign_world_defender_hero(
    db_session, city, second_city, user
):
    other_world = _other_world(db_session)
    foreign_hero = models.Hero(
        user_id=user.id,
        world_id=other_world.id,
        city_id=second_city.id,
        status="home",
        health=100,
    )
    db_session.add(foreign_hero)
    db_session.commit()

    with pytest.raises(ValueError, match="Defender hero"):
        combat.resolve_battle(
            city,
            second_city,
            {"basic_infantry": 12},
            defender_hero=foreign_hero,
        )
    assert foreign_hero.health == 100


def test_parallel_combat_oasis_rejects_invalid_army(db_session, city):
    oasis = models.Oasis(
        world_id=city.world_id,
        x=13,
        y=13,
        resource_type="iron",
        bonus_percent=15,
        troops={"basic_infantry": 4},
    )
    db_session.add(oasis)
    db_session.commit()

    with pytest.raises(ValueError, match="troop amount"):
        combat.resolve_oasis_battle(city, oasis, {"noble": -1})

    assert oasis.troops == {"basic_infantry": 4}


def test_parallel_combat_loot_debits_equal_reported_credits(db_session, city):
    target = models.City(
        name="Resource conservation target",
        world_id=city.world_id,
        owner_id=None,
        x=27,
        y=27,
        wood=200.25,
        stone=100.5,
        iron=80.0,
        gold=37.75,
    )
    db_session.add(target)
    db_session.commit()
    attack_before = {r: getattr(city, r) for r in balance.RESOURCE_FIELDS}
    defend_before = {r: getattr(target, r) for r in balance.RESOURCE_FIELDS}

    result = combat.resolve_battle(
        city, target, {"basic_infantry": 30}, seed="conservation"
    )

    assert result["outcome"] == "attacker_victory"
    max_carry = (
        result["attacker_survivors"]["basic_infantry"]
        * balance.UNIT_COMBAT_STATS["basic_infantry"]["carry"]
    )
    assert sum(result["loot"].values()) <= max_carry
    for resource, amount in result["loot"].items():
        assert 0 <= amount <= defend_before[resource]
        assert getattr(target, resource) == pytest.approx(defend_before[resource] - amount)
        assert getattr(city, resource) == pytest.approx(attack_before[resource] + amount)
