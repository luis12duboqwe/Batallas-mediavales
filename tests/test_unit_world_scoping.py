from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.services import balance
from app.services import event as event_service
from app.services import production, troops


FIXED_NOW = datetime(2026, 8, 18, 20, 30, tzinfo=timezone.utc)


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def test_world_event_affects_only_its_world(db_session, city, user, monkeypatch):
    monkeypatch.setattr(event_service, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(production, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(troops, "utc_now", lambda: FIXED_NOW)

    second_world = models.World(
        name="Event World",
        speed_modifier=1.0,
        resource_modifier=1.0,
        map_size=30,
        is_active=True,
    )
    db_session.add(second_world)
    db_session.flush()

    second_city = models.City(
        name="Second Capital",
        owner_id=user.id,
        world_id=second_world.id,
        x=5,
        y=5,
        tile_type="grass",
        wood=1000.0,
        stone=1000.0,
        iron=1000.0,
        gold=1000.0,
        last_production=FIXED_NOW,
    )
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, 1000.0)
    city.last_production = FIXED_NOW
    db_session.add(second_city)
    db_session.flush()

    db_session.add_all(
        [
            models.Building(city_id=city.id, name="barracks", level=1),
            models.Building(city_id=second_city.id, name="barracks", level=1),
            models.WorldEvent(
                world_id=second_world.id,
                name="World 2 boost",
                description="Only world two is accelerated",
                start_time=FIXED_NOW - timedelta(hours=1),
                end_time=FIXED_NOW + timedelta(hours=1),
                modifiers={
                    "production_speed": 2.0,
                    "troop_training_speed": 0.5,
                },
            ),
        ]
    )
    db_session.commit()
    db_session.refresh(city)
    db_session.refresh(second_city)

    world_one_rates = production.get_production_per_hour(db_session, city)
    world_two_rates = production.get_production_per_hour(db_session, second_city)
    assert world_one_rates == pytest.approx(balance.PRODUCTION_RATES_PER_HOUR)
    assert world_two_rates == pytest.approx(
        {
            resource: rate * 2.0
            for resource, rate in balance.PRODUCTION_RATES_PER_HOUR.items()
        }
    )

    world_one_queue = troops.queue_training(
        db_session, city, "basic_infantry", 1
    )
    world_two_queue = troops.queue_training(
        db_session, second_city, "basic_infantry", 1
    )

    assert (_aware(world_one_queue.finish_time) - FIXED_NOW).total_seconds() == pytest.approx(45.0)
    assert (_aware(world_two_queue.finish_time) - FIXED_NOW).total_seconds() == pytest.approx(22.5)
