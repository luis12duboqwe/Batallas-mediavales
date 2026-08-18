from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.services import building, production


FIXED_NOW = datetime(2026, 8, 18, 19, 0, tzinfo=timezone.utc)


def _freeze_time(monkeypatch):
    monkeypatch.setattr(building, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(production, "utc_now", lambda: FIXED_NOW)


def test_level_two_quote_matches_exact_payment(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    town_hall = models.Building(city_id=city.id, name="town_hall", level=1)
    db_session.add(town_hall)
    city.wood = city.clay = city.iron = 5000.0
    city.last_production = FIXED_NOW
    db_session.commit()
    db_session.refresh(city)

    quote = next(
        entry
        for entry in building.get_available_buildings(db_session, city)
        if entry["name"] == "town_hall"
    )
    expected = building.calculate_upgrade_cost("town_hall", 2)
    assert quote["level"] == 1
    assert quote["cost"] == pytest.approx(expected)
    assert quote["build_time"] == building.calculate_build_time(2)

    before = {resource: getattr(city, resource) for resource in ("wood", "clay", "iron")}
    queue_entry = building.queue_upgrade(db_session, city, "town_hall")

    assert queue_entry.target_level == 2
    assert queue_entry.paid_cost == pytest.approx(expected)
    for resource, amount in expected.items():
        assert getattr(city, resource) == pytest.approx(before[resource] - amount)


def test_cancel_refunds_persisted_payment_not_recomputed_cost(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    city.wood = city.clay = city.iron = 100.0
    city.last_production = FIXED_NOW
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type="town_hall",
        target_level=9,
        finish_time=FIXED_NOW + timedelta(hours=1),
        paid_cost={"wood": 111.0, "clay": 222.0, "iron": 333.0},
    )
    db_session.add(queue_entry)
    db_session.commit()
    queue_id = queue_entry.id

    assert building.cancel_building_queue(db_session, queue_id, city.owner_id) is True

    db_session.refresh(city)
    assert city.wood == pytest.approx(100.0 + 111.0 * building.REFUND_FACTOR)
    assert city.clay == pytest.approx(100.0 + 222.0 * building.REFUND_FACTOR)
    assert city.iron == pytest.approx(100.0 + 333.0 * building.REFUND_FACTOR)
    assert db_session.query(models.BuildingQueue).filter_by(id=queue_id).first() is None


def test_cancel_refund_respects_storage_without_destroying_existing_overflow(
    db_session, city, monkeypatch
):
    _freeze_time(monkeypatch)
    city.wood = 4990.0
    city.clay = 6000.0
    city.iron = 4995.0
    city.last_production = FIXED_NOW
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type="town_hall",
        target_level=1,
        finish_time=FIXED_NOW + timedelta(hours=1),
        paid_cost={"wood": 100.0, "clay": 100.0, "iron": 100.0},
    )
    db_session.add(queue_entry)
    db_session.commit()

    building.cancel_building_queue(db_session, queue_entry.id, city.owner_id)

    db_session.refresh(city)
    assert city.wood == 5000.0
    assert city.clay == 6000.0
    assert city.iron == 5000.0


def test_completed_queue_cannot_be_cancelled_for_refund(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    city.wood = city.clay = city.iron = 100.0
    city.last_production = FIXED_NOW
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type="town_hall",
        target_level=1,
        finish_time=FIXED_NOW,
        paid_cost={"wood": 260.0, "clay": 200.0, "iron": 150.0},
    )
    db_session.add(queue_entry)
    db_session.commit()

    with pytest.raises(ValueError, match="can no longer be cancelled"):
        building.cancel_building_queue(db_session, queue_entry.id, city.owner_id)

    db_session.expire_all()
    assert db_session.query(models.BuildingQueue).filter_by(id=queue_entry.id).first() is not None
    assert db_session.query(models.City).filter_by(id=city.id).one().wood == 100.0


def test_unknown_building_cannot_be_queued(db_session, city):
    with pytest.raises(ValueError, match="Unknown building type"):
        building.queue_upgrade(db_session, city, "castle_of_free_resources")


def test_due_queue_completion_deletes_queue_before_side_effects(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    building_row = models.Building(city_id=city.id, name="town_hall", level=0)
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type="town_hall",
        target_level=1,
        finish_time=FIXED_NOW - timedelta(seconds=1),
        paid_cost={"wood": 260.0, "clay": 200.0, "iron": 150.0},
    )
    db_session.add_all([building_row, queue_entry])
    db_session.commit()

    observed = {}

    def side_effect(session, info):
        observed["queue_count"] = session.query(models.BuildingQueue).count()
        observed["level"] = (
            session.query(models.Building)
            .filter_by(city_id=city.id, name="town_hall")
            .one()
            .level
        )

    monkeypatch.setattr(building, "_run_completion_side_effects", side_effect)

    finished = building.process_building_queues(db_session)

    assert finished == [
        {"city_id": city.id, "building_type": "town_hall", "target_level": 1}
    ]
    assert observed == {"queue_count": 0, "level": 1}
