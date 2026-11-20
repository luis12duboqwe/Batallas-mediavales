"""Regression coverage for the BM-0040 compatibility economy wrappers."""

import pytest

from app.services import balance, economy


@pytest.mark.parametrize(
    ("unit", "count", "population"),
    [
        ("basic_infantry", 10, 10),
        ("fast_cavalry", 10, 20),
        ("heavy_cavalry", 10, 30),
        ("catapult", 10, 50),
        ("noble", 10, 50),
    ],
)
def test_parallel_compat_population_matches_canonical_catalog(unit, count, population):
    assert balance.UNIT_CATALOG[unit]["population"] * count == population
    assert economy.calculate_population_used({unit: count}) == float(population)


def test_parallel_compat_population_mixed_army_and_legacy_values():
    army = {
        "basic_infantry": 10,
        "fast_cavalry": 3,
        "heavy_cavalry": 2,
        "catapult": 1,
        "noble": 1,
        "unknown_legacy_unit": 999,
        "spy": -8,
    }
    snapshot = dict(army)
    assert economy.calculate_population_used(army) == 32.0
    assert army == snapshot
    assert economy.calculate_population_used({}) == 0.0


@pytest.mark.parametrize("invalid", [True, False, 1.5, "2", None])
def test_parallel_compat_population_rejects_noninteger_quantities(invalid):
    with pytest.raises(ValueError, match="integer"):
        economy.calculate_population_used({"fast_cavalry": invalid})


@pytest.mark.parametrize("invalid", [True, False, 1.5, "2", None, -1, 0])
def test_parallel_compat_training_cost_rejects_invalid_amount(invalid):
    with pytest.raises(ValueError, match="positive integer"):
        economy.get_troop_cost("fast_cavalry", invalid)


@pytest.mark.parametrize("invalid", [True, False, 1.5, "2", None, -1, 0])
def test_parallel_compat_training_time_rejects_invalid_building_level(invalid):
    with pytest.raises(ValueError, match="positive integer"):
        economy.get_training_time("fast_cavalry", invalid)


def test_parallel_compat_valid_quotes_preserve_canonical_values():
    assert economy.get_troop_cost("fast_cavalry", 2) == {
        resource: cost * 2
        for resource, cost in balance.UNIT_CATALOG["fast_cavalry"]["training_cost"].items()
    }
    assert economy.get_training_time("fast_cavalry", 1) == float(
        balance.UNIT_CATALOG["fast_cavalry"]["training_time_seconds"]
    )
