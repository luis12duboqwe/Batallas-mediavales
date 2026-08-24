import json

import pytest

from app import models
from app.services import balance, combat


def _restore_resources(city, snapshot):
    for resource, value in snapshot.items():
        setattr(city, resource, value)


def test_combat_rounds_are_reproducible_from_audit_seed(db_session, city, second_city):
    defender_troop = models.Troop(
        city_id=second_city.id,
        unit_type="basic_infantry",
        quantity=18,
    )
    db_session.add(defender_troop)
    db_session.commit()

    attacker_resources = {
        resource: float(getattr(city, resource)) for resource in balance.RESOURCE_FIELDS
    }
    defender_resources = {
        resource: float(getattr(second_city, resource))
        for resource in balance.RESOURCE_FIELDS
    }

    result_one = combat.resolve_battle(
        city,
        second_city,
        {"basic_infantry": 30, "archer": 10},
        seed="bm0064-replay-seed",
    )

    _restore_resources(city, attacker_resources)
    _restore_resources(second_city, defender_resources)
    result_two = combat.resolve_battle(
        city,
        second_city,
        {"basic_infantry": 30, "archer": 10},
        seed="bm0064-replay-seed",
    )

    for key in (
        "attacker_losses",
        "defender_losses",
        "attacker_survivors",
        "defender_survivors",
        "loot",
        "rounds",
        "round_count",
        "outcome",
        "moral",
        "luck",
        "effective_attack",
        "defense_value",
    ):
        assert result_two[key] == result_one[key]

    assert result_one["seed"] == "bm0064-replay-seed"
    assert result_one["combat_version"] == combat.COMBAT_ALGORITHM_VERSION
    assert 0 <= result_one["round_count"] <= combat.COMBAT_MAX_ROUNDS
    assert len(result_one["rounds"]) == result_one["round_count"]
    for round_data in result_one["rounds"]:
        assert balance.LUCK_MIN <= round_data["luck"] <= balance.LUCK_MAX
        assert balance.MORALE_MIN <= round_data["moral"] <= balance.MORALE_MAX

    report = json.loads(
        combat.build_battle_report_content(city, second_city, result_one)
    )
    assert report["combat"]["seed"] == "bm0064-replay-seed"
    assert report["combat"]["algorithm_version"] == combat.COMBAT_ALGORITHM_VERSION
    assert report["combat"]["round_count"] == result_one["round_count"]
    assert report["combat"]["rounds"] == result_one["rounds"]


def test_different_seeds_change_luck_stream(db_session, city, second_city):
    db_session.add(
        models.Troop(
            city_id=second_city.id,
            unit_type="basic_infantry",
            quantity=20,
        )
    )
    db_session.commit()

    first = combat.resolve_battle(
        city,
        second_city,
        {"basic_infantry": 25},
        seed="seed-a",
    )
    second = combat.resolve_battle(
        city,
        second_city,
        {"basic_infantry": 25},
        seed="seed-b",
    )

    first_luck = [round_data["luck"] for round_data in first["rounds"]]
    second_luck = [round_data["luck"] for round_data in second["rounds"]]
    assert first_luck
    assert second_luck
    assert first_luck != second_luck


def test_barbarian_loyalty_drop_is_seeded_and_player_city_never_conquered(
    db_session, city, second_city
):
    barbarian = models.City(
        name="Seeded Barbarian",
        owner_id=None,
        world_id=city.world_id,
        x=8,
        y=8,
        loyalty=100.0,
        wood=1000.0,
        stone=1000.0,
        iron=1000.0,
        gold=1000.0,
    )
    db_session.add(barbarian)
    db_session.commit()

    result_one = combat.resolve_battle(
        city,
        barbarian,
        {"noble": 1},
        seed="loyalty-seed",
    )
    first_drop = result_one["loyalty_change"]
    assert balance.BARBARIAN_LOYALTY_DROP_MIN <= first_drop <= balance.BARBARIAN_LOYALTY_DROP_MAX
    assert result_one["conquest"] is False

    barbarian.loyalty = 100.0
    barbarian.owner_id = None
    for resource in balance.RESOURCE_FIELDS:
        setattr(barbarian, resource, 1000.0)
    result_two = combat.resolve_battle(
        city,
        barbarian,
        {"noble": 1},
        seed="loyalty-seed",
    )
    assert result_two["loyalty_change"] == first_drop

    player_result = combat.resolve_battle(
        city,
        second_city,
        {"noble": 1},
        seed="player-city-seed",
    )
    assert player_result["outcome"] == "attacker_victory"
    assert player_result["loyalty_change"] == 0
    assert player_result["conquest"] is False
    assert second_city.owner_id is not None


def test_loot_respects_surviving_carry_and_four_resource_catalog(
    db_session, city
):
    barbarian = models.City(
        name="Loot Barbarian",
        owner_id=None,
        world_id=city.world_id,
        x=9,
        y=9,
        wood=1000.0,
        stone=1000.0,
        iron=1000.0,
        gold=1000.0,
    )
    db_session.add(barbarian)
    db_session.commit()

    attackers = {"basic_infantry": 10}
    result = combat.resolve_battle(
        city,
        barbarian,
        attackers,
        seed="loot-seed",
    )

    assert set(result["loot"]) == set(balance.RESOURCE_FIELDS)
    carry = (
        result["attacker_survivors"]["basic_infantry"]
        * balance.UNIT_COMBAT_STATS["basic_infantry"]["carry"]
    )
    assert sum(result["loot"].values()) <= carry
    assert all(value >= 0 for value in result["loot"].values())


def test_round_count_is_bounded_even_for_long_stalemates(db_session, city, second_city):
    db_session.add(
        models.Troop(
            city_id=second_city.id,
            unit_type="heavy_infantry",
            quantity=300,
        )
    )
    db_session.commit()

    result = combat.resolve_battle(
        city,
        second_city,
        {"heavy_infantry": 300},
        seed="bounded-rounds",
    )

    assert result["round_count"] <= combat.COMBAT_MAX_ROUNDS
    assert result["outcome"] in {
        "attacker_victory",
        "defender_victory",
        "mutual_destruction",
        "stalemate",
    }
