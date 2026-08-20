from datetime import timedelta

import pytest

from app import models
from app.services import troops, unit_catalog
from app.utils import utc_now


def test_training_rejects_population_overflow_without_spending(db_session, city):
    city.population_max = 5
    city.wood = city.clay = city.iron = 5000
    db_session.add(models.Building(city_id=city.id, name="barracks", level=1))
    db_session.commit()
    db_session.refresh(city)

    before = (city.wood, city.clay, city.iron)

    with pytest.raises(ValueError, match="population capacity"):
        troops.queue_training(db_session, city, "basic_infantry", 6)

    db_session.refresh(city)
    assert (city.wood, city.clay, city.iron) == before
    assert db_session.query(models.TroopQueue).filter_by(city_id=city.id).count() == 0


def test_population_reservation_counts_home_away_returning_and_queue(
    db_session, city, second_city
):
    city.population_max = 20
    db_session.add(
        models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=4)
    )
    db_session.add(
        models.Movement(
            origin_city_id=city.id,
            target_city_id=second_city.id,
            movement_type="reinforce",
            troops={"basic_infantry": 3},
            resources={},
            spy_count=0,
            arrival_time=utc_now() + timedelta(hours=1),
            speed_used=1.0,
            world_id=city.world_id,
            status="ongoing",
        )
    )
    db_session.add(
        models.Movement(
            origin_city_id=second_city.id,
            target_city_id=city.id,
            movement_type="return",
            troops={"basic_infantry": 2},
            resources={},
            spy_count=0,
            arrival_time=utc_now() + timedelta(hours=1),
            speed_used=1.0,
            world_id=city.world_id,
            status="ongoing",
        )
    )
    db_session.add(
        models.TroopQueue(
            city_id=city.id,
            troop_type="basic_infantry",
            amount=5,
            finish_time=utc_now() + timedelta(hours=1),
            paid_cost={},
        )
    )
    db_session.commit()
    db_session.refresh(city)

    assert unit_catalog.get_population_used(db_session, city) == 9
    assert unit_catalog.get_population_reserved_for_training(db_session, city.id) == 5
    assert unit_catalog.get_population_available(db_session, city) == 6


def test_unit_availability_exposes_population_and_upkeep(db_session, city):
    city.population_max = 1
    db_session.add(models.Building(city_id=city.id, name="barracks", level=1))
    db_session.add(
        models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=1)
    )
    db_session.commit()
    db_session.refresh(city)

    available = {
        entry["unit_type"]: entry
        for entry in unit_catalog.get_availability(db_session, city)
    }
    infantry = available["basic_infantry"]

    assert infantry["population_cost"] == 1
    assert infantry["population_available"] == 0
    assert infantry["population_capacity_met"] is False
    assert infantry["upkeep_per_hour"] == 0.0
    assert infantry["can_train"] is False
