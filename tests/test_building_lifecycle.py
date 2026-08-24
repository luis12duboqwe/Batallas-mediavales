from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.services import balance, building, production, unit_catalog


FIXED_NOW = datetime(2026, 8, 18, 19, 0, tzinfo=timezone.utc)


def _freeze_time(monkeypatch):
    monkeypatch.setattr(building, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(production, "utc_now", lambda: FIXED_NOW)


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _set_resources(city, amount: float) -> None:
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, amount)


def test_level_two_quote_matches_exact_payment(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    town_hall = models.Building(city_id=city.id, name="town_hall", level=1)
    db_session.add(town_hall)
    _set_resources(city, 5000.0)
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
    assert quote["max_level"] == balance.BUILDING_MAX_LEVELS["town_hall"]
    assert quote["cost"] == pytest.approx(expected)
    assert quote["build_time"] == building.calculate_build_time("town_hall", 2)

    before = {
        resource: float(getattr(city, resource))
        for resource in balance.RESOURCE_FIELDS
    }
    queue_entry = building.queue_upgrade(db_session, city, "town_hall")

    assert queue_entry.target_level == 2
    assert queue_entry.paid_cost == pytest.approx(expected)
    assert _aware(queue_entry.finish_time) == FIXED_NOW + timedelta(
        seconds=balance.get_building_build_time("town_hall", 2)
    )
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(city, resource) == pytest.approx(
            before[resource] - expected.get(resource, 0.0)
        )


def test_catalog_exposes_academy_effects_and_four_resource_costs(db_session, city):
    _set_resources(city, 10000.0)
    db_session.add_all(
        [
            models.Building(city_id=city.id, name="town_hall", level=4),
            models.Building(city_id=city.id, name="barracks", level=3),
        ]
    )
    db_session.commit()

    catalog = {entry["name"]: entry for entry in building.get_available_buildings(db_session, city)}
    academy = catalog["academy"]
    assert academy["display_name"] == "Academia Militar"
    assert academy["requirements_met"] is True
    assert academy["effect"] == {
        "type": "research_access",
        "queue_slots": balance.RESEARCH_QUEUE_SLOTS_PER_CITY,
    }
    assert set(academy["cost"]) == set(balance.RESOURCE_FIELDS)
    assert academy["build_time"] == balance.get_building_build_time("academy", 1)

    assert catalog["wall"]["effect"]["per_level"] == balance.WALL_BONUS_PER_LEVEL
    assert catalog["market"]["effect"]["per_level"] == balance.MERCHANT_CAPACITY_PER_LEVEL
    assert catalog["farm"]["effect"]["per_level"] == balance.POPULATION_PER_FARM_LEVEL
    assert catalog["warehouse"]["effect"]["per_level"] == balance.STORAGE_PER_WAREHOUSE_LEVEL


def test_max_level_building_cannot_be_queued(db_session, city):
    maximum = balance.BUILDING_MAX_LEVELS["wall"]
    db_session.add(models.Building(city_id=city.id, name="wall", level=maximum))
    db_session.commit()

    quote = next(
        entry
        for entry in building.get_available_buildings(db_session, city)
        if entry["name"] == "wall"
    )
    assert quote["is_max_level"] is True
    assert quote["can_upgrade"] is False
    assert quote["cost"] == {}
    assert quote["build_time"] == 0

    with pytest.raises(ValueError, match="Maximum building level"):
        building.queue_upgrade(db_session, city, "wall")


def test_farm_completion_adds_effective_capacity_without_overwriting_base(
    db_session, city, monkeypatch
):
    _freeze_time(monkeypatch)
    city.population_max = 120
    farm = models.Building(city_id=city.id, name="farm", level=0)
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type="farm",
        target_level=1,
        finish_time=FIXED_NOW - timedelta(seconds=1),
        paid_cost={},
    )
    db_session.add_all([farm, queue_entry])
    db_session.commit()

    building.process_building_queues(db_session)
    db_session.refresh(city)
    db_session.expire(city, ["buildings"])

    assert city.population_max == 120
    assert unit_catalog.get_population_capacity(city) == (
        120 + balance.POPULATION_PER_FARM_LEVEL
    )


def test_cancel_refunds_persisted_payment_not_recomputed_cost(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    _set_resources(city, 100.0)
    city.last_production = FIXED_NOW
    paid_cost = {"wood": 111.0, "stone": 222.0, "iron": 333.0}
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type="town_hall",
        target_level=9,
        finish_time=FIXED_NOW + timedelta(hours=1),
        paid_cost=paid_cost,
    )
    db_session.add(queue_entry)
    db_session.commit()
    queue_id = queue_entry.id

    assert building.cancel_building_queue(db_session, queue_id, city.owner_id) is True

    db_session.refresh(city)
    for resource in balance.RESOURCE_FIELDS:
        expected = 100.0 + paid_cost.get(resource, 0.0) * building.REFUND_FACTOR
        assert getattr(city, resource) == pytest.approx(expected)
    assert db_session.query(models.BuildingQueue).filter_by(id=queue_id).first() is None


def test_cancel_refund_respects_storage_without_destroying_existing_overflow(
    db_session, city, monkeypatch
):
    _freeze_time(monkeypatch)
    city.wood = 4990.0
    city.stone = 6000.0
    city.iron = 4995.0
    city.gold = 4999.0
    city.last_production = FIXED_NOW
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type="town_hall",
        target_level=1,
        finish_time=FIXED_NOW + timedelta(hours=1),
        paid_cost={"wood": 100.0, "stone": 100.0, "iron": 100.0},
    )
    db_session.add(queue_entry)
    db_session.commit()

    building.cancel_building_queue(db_session, queue_entry.id, city.owner_id)

    db_session.refresh(city)
    assert city.wood == 5000.0
    assert city.stone == 6000.0
    assert city.iron == 5000.0
    assert city.gold == 4999.0


def test_completed_queue_cannot_be_cancelled_for_refund(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    _set_resources(city, 100.0)
    city.last_production = FIXED_NOW
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type="town_hall",
        target_level=1,
        finish_time=FIXED_NOW,
        paid_cost={"wood": 260.0, "stone": 200.0, "iron": 150.0},
    )
    db_session.add(queue_entry)
    db_session.commit()

    with pytest.raises(ValueError, match="can no longer be cancelled"):
        building.cancel_building_queue(db_session, queue_entry.id, city.owner_id)

    db_session.expire_all()
    assert db_session.query(models.BuildingQueue).filter_by(id=queue_entry.id).first() is not None
    persisted = db_session.query(models.City).filter_by(id=city.id).one()
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(persisted, resource) == 100.0


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
        paid_cost={"wood": 260.0, "stone": 200.0, "iron": 150.0},
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
