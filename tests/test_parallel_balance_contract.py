"""Focused regression tests for the canonical, versioned economy contract.

Only the shared balance module is exercised: these tests do not change
world rules, DB schemas or transaction ownership.
"""

import math
from decimal import Decimal

import pytest

from app.services import balance


def test_balance_version_and_four_resource_baseline_remain_unchanged():
    assert balance.BALANCE_VERSION == "2026.08.23-bm0063.1"
    assert balance.COMMERCE_RULES_VERSION == "2026.08.24-bm0066-v1"
    assert balance.RESOURCE_FIELDS == ("wood", "stone", "iron", "gold")
    assert balance.CITY_STARTING_RESOURCES == dict.fromkeys(balance.RESOURCE_FIELDS, 500.0)
    assert balance.PRODUCTION_RATES_PER_HOUR == {
        "wood": 15.0,
        "stone": 12.0,
        "iron": 10.0,
        "gold": 8.0,
    }
    assert balance.STORAGE_BASE_CAPACITY == 5000.0
    assert balance.STORAGE_PER_WAREHOUSE_LEVEL == 2000.0
    assert balance.POPULATION_PER_FARM_LEVEL == 25
    assert balance.CAMP_PRODUCTION_MULTIPLIER == 0.25
    assert balance.QUEUE_REFUND_FACTOR == 0.80
    assert balance.BUILDING_COST_GROWTH == 1.20


def test_building_catalog_is_unique_and_complete():
    expected = set(balance.BUILDING_ORDER)
    assert len(balance.BUILDING_ORDER) == len(expected)
    for table in (
        balance.BUILDING_COSTS,
        balance.BUILDING_DISPLAY_NAMES,
        balance.BUILDING_DESCRIPTIONS,
        balance.BUILDING_MAX_LEVELS,
        balance.BUILDING_BASE_BUILD_TIME_SECONDS,
    ):
        assert set(table) == expected
    assert set(balance.BUILDING_PREREQUISITES) <= expected

    for name in balance.BUILDING_ORDER:
        assert set(balance.BUILDING_COSTS[name]) == set(balance.RESOURCE_FIELDS)
        assert all(value > 0 for value in balance.BUILDING_COSTS[name].values())
        assert balance.BUILDING_MAX_LEVELS[name] >= 1
        assert balance.BUILDING_BASE_BUILD_TIME_SECONDS[name] > 0
        for prerequisite, needed_level in balance.BUILDING_PREREQUISITES.get(name, {}).items():
            assert prerequisite in expected
            assert 1 <= needed_level <= balance.BUILDING_MAX_LEVELS[prerequisite]


@pytest.mark.parametrize("building_type", balance.BUILDING_ORDER)
def test_valid_building_levels_keep_canonical_cost_growth_and_duration(building_type):
    maximum = balance.BUILDING_MAX_LEVELS[building_type]
    base_cost = balance.BUILDING_COSTS[building_type]
    base_duration = balance.BUILDING_BASE_BUILD_TIME_SECONDS[building_type]

    for level in sorted({1, 2, maximum // 2 or 1, maximum}):
        actual = balance.get_building_cost(building_type, level)
        assert set(actual) == set(balance.RESOURCE_FIELDS)
        for resource, initial_cost in base_cost.items():
            expected = initial_cost * balance.BUILDING_COST_GROWTH ** (level - 1)
            assert math.isfinite(actual[resource])
            assert actual[resource] == pytest.approx(expected)
        assert balance.get_building_build_time(building_type, level) == base_duration * level

    assert balance.get_building_max_level(building_type) == maximum


def test_fractional_currency_is_not_silently_rounded_or_changed():
    # Costs are floats by historical contract; no implicit integer rounding.
    cost = balance.get_building_cost("town_hall", 3)
    assert cost["wood"] == pytest.approx(374.4)
    assert balance.get_building_build_time("town_hall", 3) == 900
    assert cost["wood"] * balance.QUEUE_REFUND_FACTOR == pytest.approx(299.52)
    cost["wood"] = -1
    assert balance.BUILDING_COSTS["town_hall"]["wood"] == 260.0
    assert balance.get_building_cost("town_hall", 3)["wood"] == pytest.approx(374.4)


@pytest.mark.parametrize("building_type", balance.BUILDING_ORDER)
def test_building_levels_outside_canonical_range_fail_closed(building_type):
    maximum = balance.BUILDING_MAX_LEVELS[building_type]
    for calculator in (balance.get_building_cost, balance.get_building_build_time):
        for level in (-10, -1, 0, maximum + 1, 10**6):
            with pytest.raises(ValueError):
                calculator(building_type, level)


@pytest.mark.parametrize(
    "invalid_level",
    [False, True, 1.0, 1.5, -0.5, "1", None, Decimal("2"), float("nan"), float("inf")],
)
def test_invalid_building_level_types_are_rejected_consistently(invalid_level):
    for calculator in (balance.get_building_cost, balance.get_building_build_time):
        with pytest.raises(ValueError, match="integer"):
            calculator("barracks", invalid_level)


def test_invalid_building_name_is_rejected_by_all_calculators():
    for calculator in (
        balance.get_building_cost,
        balance.get_building_build_time,
    ):
        with pytest.raises(ValueError, match="Unknown building"):
            calculator("not_a_building", 1)
    with pytest.raises(ValueError, match="Unknown building"):
        balance.get_building_max_level("not_a_building")


@pytest.mark.parametrize("level", [0, 1, 2, 10, 20])
def test_storage_and_population_follow_canonical_capacity_formulas(level):
    assert balance.get_storage_capacity(level) == 5000.0 + 2000.0 * level
    assert balance.get_population_capacity("city", level) == 100 + 25 * level
    assert balance.get_population_capacity("camp", level) == 50


def test_negative_persisted_levels_preserve_legacy_zero_floor():
    for level in (-1, -20):
        assert balance.get_storage_capacity(level) == balance.STORAGE_BASE_CAPACITY
        assert balance.get_population_capacity("city", level) == balance.CITY_POPULATION_MAX
        assert balance.get_population_capacity("camp", level) == balance.CAMP_POPULATION_MAX


@pytest.mark.parametrize(
    "invalid_level",
    [True, False, 2.0, 2.9, -1.5, "2", None, Decimal("2"), float("nan"), float("inf")],
)
def test_capacity_calculators_reject_invalid_level_types(invalid_level):
    with pytest.raises(ValueError, match="integer"):
        balance.get_storage_capacity(invalid_level)
    for settlement_type in ("city", "camp"):
        with pytest.raises(ValueError, match="integer"):
            balance.get_population_capacity(settlement_type, invalid_level)


@pytest.mark.parametrize("settlement_type", ["village", "", None, "CAMP", "City"])
def test_unknown_settlement_types_cannot_assume_city_capacity(settlement_type):
    with pytest.raises(ValueError, match="Unknown settlement type"):
        balance.get_population_capacity(settlement_type, 2)


def test_unit_catalog_and_legacy_aliases_have_one_authoritative_definition():
    expected = set(balance.UNIT_ORDER)
    assert len(balance.UNIT_ORDER) == len(expected)
    assert set(balance.UNIT_CATALOG) == expected
    assert set(balance.UNIT_SPEED) == expected
    assert set(balance.UNIT_COMBAT_STATS) == expected
    assert set(balance.UNIT_DISPLAY_NAMES) == expected
    assert set(balance.LEGACY_UNIT_ALIASES).isdisjoint(expected)
    assert set(balance.LEGACY_UNIT_ALIASES.values()) <= expected

    for unit_type in balance.UNIT_ORDER:
        unit = balance.UNIT_CATALOG[unit_type]
        assert set(unit["training_cost"]) == set(balance.RESOURCE_FIELDS)
        assert unit["training_time_seconds"] > 0
        assert unit["population"] > 0
        assert unit["upkeep_per_hour"] > 0
        assert balance.UNIT_SPEED[unit_type] > 0
        assert all(amount > 0 for amount in unit["training_cost"].values())
        for prerequisite_map in ("training_requirements", "research_requirements"):
            for required, level in unit[prerequisite_map].items():
                assert required in balance.BUILDING_MAX_LEVELS
                assert 1 <= level <= balance.BUILDING_MAX_LEVELS[required]
        if unit["researchable"]:
            assert set(unit["research_cost"]) == set(balance.RESOURCE_FIELDS)
            assert all(amount > 0 for amount in unit["research_cost"].values())
            assert unit["research_time_seconds"] > 0
        else:
            assert not unit["research_cost"]
            assert unit["research_time_seconds"] == 0

    aliases = balance.unit_combat_stats_with_legacy_aliases()
    assert set(aliases) == expected | set(balance.LEGACY_UNIT_ALIASES)
    for legacy, canonical in balance.LEGACY_UNIT_ALIASES.items():
        assert aliases[legacy] == aliases[canonical] == balance.UNIT_COMBAT_STATS[canonical]
        assert aliases[legacy] is not aliases[canonical]
    aliases["basic_infantry"]["attack"] = -100
    assert balance.UNIT_COMBAT_STATS["basic_infantry"]["attack"] == 10


def test_upkeep_and_settlement_production_have_consistent_fixed_units():
    basic_upkeep = balance.UNIT_CATALOG["basic_infantry"]["upkeep_per_hour"]
    assert 20 * basic_upkeep == pytest.approx(0.40)
    assert balance.PRODUCTION_RATES_PER_HOUR["gold"] * balance.CAMP_PRODUCTION_MULTIPLIER == 2.0
    assert balance.get_population_capacity("city", 20) == 600
    assert balance.get_population_capacity("camp", 20) == 50


def test_expansion_costs_and_points_prevent_promotion_arbitrage():
    for resource in balance.RESOURCE_FIELDS:
        camp = balance.CAMP_FOUNDING_COST.get(resource, 0.0)
        promotion = balance.CAMP_PROMOTION_COST.get(resource, 0.0)
        city = balance.CITY_FOUNDING_COST.get(resource, 0.0)
        assert camp + promotion == pytest.approx(city)
    points = balance.SETTLEMENT_EXPANSION_POINT_COSTS
    assert points["camp"] + balance.CAMP_PROMOTION_POINT_COST == points["city"]
    assert balance.EXPANSION_POINTS_PER_COMPLETION == {"church": 1, "cathedral": 3}
    assert set(balance.CAMP_ALLOWED_BUILDINGS) == {"barracks", "wall", "warehouse"}


def test_snapshot_matches_authority_and_is_deeply_independent():
    view = balance.snapshot()
    assert view["version"] == balance.BALANCE_VERSION
    assert view["resources"] == list(balance.RESOURCE_FIELDS)
    assert view["production"]["base_rates_per_hour"] == balance.PRODUCTION_RATES_PER_HOUR
    assert view["buildings"]["order"] == balance.BUILDING_ORDER
    assert view["units"]["order"] == balance.UNIT_ORDER
    assert view["units"]["maintenance_resource"] == "gold"
    assert view["market"]["rules_version"] == balance.COMMERCE_RULES_VERSION

    view["buildings"]["catalog"]["barracks"]["base_cost"]["wood"] = -9
    view["units"]["catalog"]["noble"]["training_cost"]["gold"] = -9
    view["events"]["default_modifiers"]["production_speed"] = -9
    view["expansion"]["camp_founding_cost"]["wood"] = -9
    assert balance.BUILDING_COSTS["barracks"]["wood"] == 200.0
    assert balance.UNIT_CATALOG["noble"]["training_cost"]["gold"] == 100.0
    assert balance.EVENT_DEFAULT_MODIFIERS["production_speed"] == 1.0
    assert balance.CAMP_FOUNDING_COST["wood"] == 300.0
    second_view = balance.snapshot()
    assert second_view["buildings"]["catalog"]["barracks"]["base_cost"]["wood"] == 200.0
    assert second_view["units"]["catalog"]["noble"]["training_cost"]["gold"] == 100.0
