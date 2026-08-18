import threading

import pytest

from app import models
from app.database import SessionLocal, engine
from app.services import world_membership


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="World onboarding lock guarantee requires PostgreSQL row locks",
)


def test_concurrent_join_creates_one_membership_and_one_starting_city(db_session, user):
    world = db_session.query(models.World).first()
    world_id = world.id
    user_id = user.id
    barrier = threading.Barrier(2)
    results: list[tuple[int, int]] = []
    errors: list[Exception] = []
    result_lock = threading.Lock()

    def runner() -> None:
        session = SessionLocal()
        try:
            loaded_user = session.query(models.User).filter(models.User.id == user_id).one()
            barrier.wait(timeout=5)
            membership = world_membership.join_world(session, loaded_user, world_id)
            with result_lock:
                results.append((membership.id, membership.starting_city_id))
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
        assert not thread.is_alive(), "Concurrent world join did not finish"

    assert errors == []
    assert len(results) == 2
    assert results[0] == results[1]

    db_session.expire_all()
    assert (
        db_session.query(models.PlayerWorld)
        .filter(
            models.PlayerWorld.user_id == user_id,
            models.PlayerWorld.world_id == world_id,
        )
        .count()
        == 1
    )
    cities = (
        db_session.query(models.City)
        .filter(
            models.City.owner_id == user_id,
            models.City.world_id == world_id,
        )
        .all()
    )
    assert len(cities) == 1
    assert cities[0].id == results[0][1]
