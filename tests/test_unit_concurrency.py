import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.database import SessionLocal, engine
from app.services import balance
from app.services import premium as premium_service
from app.services import research as research_service
from app.services import troops as troop_service


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Unit lifecycle concurrency guarantees require PostgreSQL row locks",
)


def _run_two(callback):
    barrier = threading.Barrier(2)
    results = []
    errors = []
    guard = threading.Lock()

    def runner():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            value = callback(session)
            with guard:
                results.append(value)
        except Exception as exc:  # losing transaction may be expected
            session.rollback()
            with guard:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=runner) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent unit transaction did not finish"

    return results, errors


def test_two_research_requests_create_one_queue_and_one_charge(db_session, city):
    db_session.add_all(
        [
            models.Building(city_id=city.id, name="academy", level=1),
            models.Building(city_id=city.id, name="barracks", level=3),
        ]
    )
    city.wood = 700.0
    city.stone = 600.0
    city.iron = 500.0
    city.gold = 150.0
    # This test measures exactly-once charging, not passive production. Pin the
    # economic clock ahead of both worker threads so runner speed cannot add a
    # fractional production tick and make the resource assertion flaky.
    city.last_production = datetime.now(timezone.utc) + timedelta(minutes=1)
    db_session.commit()
    city_id = city.id

    before = {resource: float(getattr(city, resource)) for resource in ("wood", "stone", "iron", "gold")}
    expected_cost = {"wood": 500.0, "stone": 400.0, "iron": 300.0, "gold": 50.0}

    def research_once(session):
        loaded_city = session.query(models.City).filter(models.City.id == city_id).one()
        row = research_service.research_tech(session, loaded_city, "heavy_infantry")
        return row.id

    results, errors = _run_two(research_once)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)

    db_session.expire_all()
    queues = (
        db_session.query(models.ResearchQueue)
        .filter_by(city_id=city_id, tech_name="heavy_infantry")
        .all()
    )
    assert len(queues) == 1
    assert (
        db_session.query(models.Research)
        .filter_by(city_id=city_id, tech_name="heavy_infantry")
        .count()
        == 0
    )
    refreshed = db_session.query(models.City).filter_by(id=city_id).one()
    for resource, amount in expected_cost.items():
        assert float(getattr(refreshed, resource)) == pytest.approx(before[resource] - amount)
    assert "heavy_infantry" not in refreshed.researched_units


def test_two_processors_complete_research_queue_once(db_session, city):
    queue = models.ResearchQueue(
        city_id=city.id,
        tech_name="heavy_infantry",
        finish_time=datetime.now(timezone.utc) - timedelta(seconds=1),
        paid_cost={"wood": 500.0, "stone": 400.0, "iron": 300.0, "gold": 50.0},
    )
    db_session.add(queue)
    db_session.commit()
    city_id = city.id

    def process_once(session):
        return len(research_service.process_research_queues(session))

    results, errors = _run_two(process_once)

    assert errors == []
    assert sorted(results) == [0, 1]

    db_session.expire_all()
    rows = (
        db_session.query(models.Research)
        .filter_by(city_id=city_id, tech_name="heavy_infantry")
        .all()
    )
    assert len(rows) == 1
    refreshed = db_session.query(models.City).filter_by(id=city_id).one()
    assert "heavy_infantry" in refreshed.researched_units
    assert db_session.query(models.ResearchQueue).filter_by(city_id=city_id).count() == 0


def test_two_training_requests_cannot_overbook_upkeep_capacity(db_session, city):
    db_session.add(models.Building(city_id=city.id, name="barracks", level=1))
    city.population_max = 1000
    # Same isolation as the research charge test: passive production must not
    # affect the exact resource-reservation assertion below.
    city.last_production = datetime.now(timezone.utc) + timedelta(minutes=1)
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, 100000.0)
    status = premium_service.get_or_create_status(db_session, city.owner)
    status.second_troop_queue = True
    db_session.add(status)
    db_session.add(city)
    db_session.commit()
    city_id = city.id

    quantity = 250
    per_unit = balance.UNIT_CATALOG["basic_infantry"]
    assert per_unit["upkeep_per_hour"] * quantity < balance.PRODUCTION_RATES_PER_HOUR["gold"]
    assert per_unit["upkeep_per_hour"] * quantity * 2 > balance.PRODUCTION_RATES_PER_HOUR["gold"]
    before = {
        resource: float(getattr(city, resource))
        for resource in balance.RESOURCE_FIELDS
    }

    def train_once(session):
        loaded_city = session.query(models.City).filter(models.City.id == city_id).one()
        return troop_service.queue_training(
            session,
            loaded_city,
            "basic_infantry",
            quantity,
        ).id

    results, errors = _run_two(train_once)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert "sustainable gold income" in str(errors[0])

    db_session.expire_all()
    queues = db_session.query(models.TroopQueue).filter_by(city_id=city_id).all()
    assert len(queues) == 1
    assert queues[0].amount == quantity
    refreshed = db_session.query(models.City).filter_by(id=city_id).one()
    for resource, unit_cost in per_unit["training_cost"].items():
        assert float(getattr(refreshed, resource)) == pytest.approx(
            before[resource] - float(unit_cost) * quantity
        )


def test_two_processors_complete_troop_queue_once(db_session, city, monkeypatch):
    queue = models.TroopQueue(
        city_id=city.id,
        troop_type="basic_infantry",
        amount=7,
        finish_time=datetime.now(timezone.utc) - timedelta(seconds=1),
        paid_cost={"wood": 350.0, "stone": 210.0, "iron": 140.0},
    )
    db_session.add(queue)
    db_session.commit()
    city_id = city.id

    monkeypatch.setattr(
        troop_service,
        "_run_training_side_effects",
        lambda session, info: None,
    )

    def process_once(session):
        return len(troop_service.process_troop_queues(session))

    results, errors = _run_two(process_once)

    assert errors == []
    assert sorted(results) == [0, 1]

    db_session.expire_all()
    troop = (
        db_session.query(models.Troop)
        .filter_by(city_id=city_id, unit_type="basic_infantry")
        .one()
    )
    assert troop.quantity == 7
    assert db_session.query(models.TroopQueue).filter_by(city_id=city_id).count() == 0
