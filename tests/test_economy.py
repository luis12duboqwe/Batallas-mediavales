import pytest

from app.services import economy


def test_building_and_troop_costs_and_population():
    cost = economy.get_building_cost("Casa Central", 2)
    assert cost["wood"] > economy.BASE_BUILDING_COSTS["Casa Central"]["wood"]

    troop_cost = economy.get_troop_cost("Lancero Común", 3)
    assert troop_cost["wood"] == economy.BASE_TROOP_COSTS["Lancero Común"]["wood"] * 3

    with pytest.raises(ValueError):
        economy.get_troop_cost("Lancero Común", 0)

    population = economy.calculate_population_used({"Lancero Común": 10})
    assert population == economy.BASE_TROOP_COSTS["Lancero Común"]["population"] * 10


def test_storage_and_training_time():
    capacity = economy.get_storage_capacity(2)
    assert capacity > economy.STORAGE_BASE_CAPACITY

    enforced = economy.enforce_storage_limits({"wood": capacity * 2}, 2)
    assert enforced["wood"] == capacity

    training_time = economy.get_training_time("Lancero Común", 2)
    assert training_time > economy.BASE_TRAINING_TIMES["Lancero Común"]
