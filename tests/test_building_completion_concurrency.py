import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.database import SessionLocal, engine
from app.services import building as building_service


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Building completion single-consumer guarantee requires PostgreSQL locks",
)


def test_two_processors_complete_due_building_once(db_session, city, monkeypatch):
    building_row = models.Building(city_id=city.id, name="town_hall", level=0)
    queue_entry = models.BuildingQueue(
        city_id=city.id,
        building_type="town_hall",
        target_level=1,
        finish_time=datetime.now(timezone.utc) - timedelta(seconds=1),
        paid_cost={"wood": 260.0, "clay": 200.0, "iron": 150.0},
    )
    db_session.add_all([building_row, queue_entry])
    db_session.commit()
    city_id = city.id

    # This test targets the authoritative queue mutation. Side effects have
    # their own services/commits and intentionally run only after queue deletion.
    monkeypatch.setattr(
        building_service,
        "_run_completion_side_effects",
        lambda session, info: None,
    )

    barrier = threading.Barrier(2)
    result_lengths: list[int] = []
    errors: list[Exception] = []
    result_lock = threading.Lock()

    def runner() -> None:
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            result = building_service.process_building_queues(session)
            with result_lock:
                result_lengths.append(len(result))
        except Exception as exc:  # pragma: no cover - asserted below on PostgreSQL
            session.rollback()
            with result_lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=runner) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent building completion did not finish"

    assert errors == []
    assert sorted(result_lengths) == [0, 1]

    db_session.expire_all()
    final_building = (
        db_session.query(models.Building)
        .filter_by(city_id=city_id, name="town_hall")
        .one()
    )
    assert final_building.level == 1
    assert db_session.query(models.BuildingQueue).filter_by(city_id=city_id).count() == 0
