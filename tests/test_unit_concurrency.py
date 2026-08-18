import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.database import SessionLocal, engine
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


def test_two_research_requests_create_one_technology_and_one_charge(db_session, city):
    db_session.add(models.Building(city_id=city.id, name="barracks", level=3))
    city.wood = 600.0
    city.clay = 500.0
    city.iron = 400.0
    city.last_production = datetime.now(timezone.utc)
    db_session.commit()
    city_id = city.id

    def research_once(session):
        loaded_city = session.query(models.City).filter(models.City.id == city_id).one()
        row = research_service.research_tech(session, loaded_city, "heavy_infantry")
        return row.id

    results, errors = _run_two(research_once)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)

    db_session.expire_all()
    rows = (
        db_session.query(models.Research)
        .filter_by(city_id=city_id, tech_name="heavy_infantry")
        .all()
    )
    assert len(rows) == 1
    refreshed = db_session.query(models.City).filter_by(id=city_id).one()
    assert refreshed.wood >= 100.0
    assert refreshed.clay >= 100.0
    assert refreshed.iron >= 100.0
    assert "heavy_infantry" in refreshed.researched_units


def test_two_processors_complete_troop_queue_once(db_session, city, monkeypatch):
    queue = models.TroopQueue(
        city_id=city.id,
        troop_type="basic_infantry",
        amount=7,
        finish_time=datetime.now(timezone.utc) - timedelta(seconds=1),
        paid_cost={"wood": 350.0, "clay": 210.0, "iron": 140.0},
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
