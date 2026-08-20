import pytest

from app.services import balance, economy


def test_building_and_troop_costs_use_canonical_keys_and_values():
    level_two = economy.get_building_cost("town_hall", 2)
    assert level_two == balance.get_building_cost("town_hall", 2)
    assert level_two["wood"] == pytest.approx(
        balance.BUILDING_COSTS["town_hall"]["wood"] * balance.BUILDING_COST_GROWTH
    )

    troop_cost = economy.get_troop_cost("basic_infantry", 3)
    assert troop_cost == {
        resource: amount * 3
        for resource, amount in balance.UNIT_CATALOG["basic_infantry"]["training_cost"].items()
    }

    with pytest.raises(ValueError):
        economy.get_troop_cost("basic_infantry", 0)

    assert economy.calculate_population_used({"basic_infantry": 10}) == 10.0


def test_storage_and_training_time_match_live_rules():
    capacity = economy.get_storage_capacity(2)
    assert capacity == (
        balance.STORAGE_BASE_CAPACITY
        + 2 * balance.STORAGE_PER_WAREHOUSE_LEVEL
    )

    enforced = economy.enforce_storage_limits({"wood": capacity * 2}, 2)
    assert enforced["wood"] == capacity

    base_time = balance.UNIT_CATALOG["basic_infantry"]["training_time_seconds"]
    assert economy.get_training_time("basic_infantry", 1) == base_time
    assert economy.get_training_time("basic_infantry", 20) == base_time
