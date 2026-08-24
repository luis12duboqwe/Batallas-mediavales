import pytest

from app.services import balance


EXPECTED_MILITARY_PROFILES = {
    "basic_infantry": {
        "cost": (50, 30, 20, 2),
        "time": 45,
        "population": 1,
        "upkeep": 0.02,
        "speed": 0.60,
        "carry": 40,
    },
    "heavy_infantry": {
        "cost": (70, 60, 50, 4),
        "time": 60,
        "population": 1,
        "upkeep": 0.03,
        "speed": 0.55,
        "carry": 30,
    },
    "archer": {
        "cost": (80, 40, 40, 4),
        "time": 50,
        "population": 1,
        "upkeep": 0.03,
        "speed": 0.70,
        "carry": 35,
    },
    "fast_cavalry": {
        "cost": (120, 80, 100, 8),
        "time": 70,
        "population": 2,
        "upkeep": 0.05,
        "speed": 1.20,
        "carry": 80,
    },
    "heavy_cavalry": {
        "cost": (200, 150, 200, 15),
        "time": 80,
        "population": 3,
        "upkeep": 0.08,
        "speed": 0.90,
        "carry": 60,
    },
    "spy": {
        "cost": (40, 40, 40, 4),
        "time": 30,
        "population": 1,
        "upkeep": 0.04,
        "speed": 1.50,
        "carry": 0,
    },
    "ram": {
        "cost": (300, 200, 150, 12),
        "time": 90,
        "population": 3,
        "upkeep": 0.06,
        "speed": 0.50,
        "carry": 0,
    },
    "catapult": {
        "cost": (350, 250, 300, 20),
        "time": 120,
        "population": 5,
        "upkeep": 0.10,
        "speed": 0.45,
        "carry": 0,
    },
    "noble": {
        "cost": (1000, 1000, 1000, 100),
        "time": 600,
        "population": 5,
        "upkeep": 0.50,
        "speed": 0.40,
        "carry": 0,
    },
}


def test_bm0063_profiles_are_fully_versioned_and_use_four_resource_training():
    assert balance.BALANCE_VERSION.endswith("bm0063.1")
    assert tuple(EXPECTED_MILITARY_PROFILES) == tuple(balance.UNIT_ORDER)

    for unit_type, expected in EXPECTED_MILITARY_PROFILES.items():
        definition = balance.UNIT_CATALOG[unit_type]
        cost_tuple = tuple(
            int(definition["training_cost"][resource])
            for resource in balance.RESOURCE_FIELDS
        )
        assert cost_tuple == expected["cost"]
        assert int(definition["training_time_seconds"]) == expected["time"]
        assert int(definition["population"]) == expected["population"]
        assert float(definition["upkeep_per_hour"]) == pytest.approx(expected["upkeep"])
        assert float(balance.UNIT_SPEED[unit_type]) == pytest.approx(expected["speed"])
        assert int(balance.UNIT_COMBAT_STATS[unit_type]["carry"]) == expected["carry"]
        assert all(definition["training_cost"][resource] > 0 for resource in balance.RESOURCE_FIELDS)
        assert definition["upkeep_per_hour"] > 0
        assert definition["population"] > 0


def test_unit_roles_have_distinct_population_and_mobility_pressure():
    assert balance.UNIT_CATALOG["fast_cavalry"]["population"] > balance.UNIT_CATALOG["archer"]["population"]
    assert balance.UNIT_CATALOG["heavy_cavalry"]["population"] > balance.UNIT_CATALOG["fast_cavalry"]["population"]
    assert balance.UNIT_CATALOG["catapult"]["population"] > balance.UNIT_CATALOG["ram"]["population"]

    assert balance.UNIT_SPEED["spy"] > balance.UNIT_SPEED["fast_cavalry"]
    assert balance.UNIT_SPEED["fast_cavalry"] > balance.UNIT_SPEED["basic_infantry"]
    assert balance.UNIT_SPEED["basic_infantry"] > balance.UNIT_SPEED["catapult"]

    assert balance.UNIT_COMBAT_STATS["fast_cavalry"]["carry"] > balance.UNIT_COMBAT_STATS["basic_infantry"]["carry"]
    assert balance.UNIT_COMBAT_STATS["heavy_cavalry"]["attack"] > balance.UNIT_COMBAT_STATS["heavy_infantry"]["attack"]
    assert balance.UNIT_COMBAT_STATS["catapult"]["def_siege"] > balance.UNIT_COMBAT_STATS["ram"]["def_siege"]


def test_population_and_upkeep_create_two_independent_army_limits():
    basic = balance.UNIT_CATALOG["basic_infantry"]
    base_gold = balance.PRODUCTION_RATES_PER_HOUR["gold"]

    camp_population = balance.CAMP_POPULATION_MAX
    camp_gold_capacity = base_gold * balance.CAMP_PRODUCTION_MULTIPLIER
    camp_by_upkeep = int(camp_gold_capacity / basic["upkeep_per_hour"])
    assert camp_population < camp_by_upkeep

    developed_city_population = balance.get_population_capacity("city", 20)
    city_by_upkeep = int(base_gold / basic["upkeep_per_hour"])
    assert city_by_upkeep < developed_city_population
    assert city_by_upkeep == 400


def test_top_tier_unit_is_not_a_fast_or_cheap_training_placeholder():
    noble = balance.UNIT_CATALOG["noble"]
    catapult = balance.UNIT_CATALOG["catapult"]
    heavy_cavalry = balance.UNIT_CATALOG["heavy_cavalry"]

    assert noble["training_time_seconds"] > catapult["training_time_seconds"]
    assert noble["training_cost"]["gold"] > heavy_cavalry["training_cost"]["gold"]
    assert noble["upkeep_per_hour"] > catapult["upkeep_per_hour"]
    assert noble["population"] >= heavy_cavalry["population"]
