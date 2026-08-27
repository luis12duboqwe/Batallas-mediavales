import threading

import pytest
from fastapi import HTTPException

from app import models
from app.database import SessionLocal, engine
from app.services import world_lifecycle

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="BM-0072 lifecycle concurrency guarantees require PostgreSQL row locks",
)


def test_concurrent_stale_lifecycle_transitions_only_one_confirms(
    db_session, user, city
):
    user.is_admin = True
    world = city.world
    world.lifecycle_status = "open"
    world.is_active = True
    world.pause_started_at = None
    db_session.commit()
    user_id = user.id
    world_id = world.id

    barrier = threading.Barrier(2)
    successes: list[str] = []
    failures: list[tuple[int, str]] = []
    lock = threading.Lock()

    def worker(target_status: str) -> None:
        session = SessionLocal()
        try:
            admin_user = session.query(models.User).filter_by(id=user_id).one()
            barrier.wait(timeout=5)
            transitioned = world_lifecycle.transition_world(
                session,
                world_id,
                target_status=target_status,
                expected_status="open",
                reason=f"Concurrent transition to {target_status}",
                admin_user=admin_user,
            )
            with lock:
                successes.append(transitioned.lifecycle_status)
        except HTTPException as exc:
            session.rollback()
            with lock:
                failures.append((exc.status_code, str(exc.detail)))
        finally:
            session.close()

    threads = [
        threading.Thread(target=worker, args=("paused",)),
        threading.Thread(target=worker, args=("closed",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent BM-0072 transition did not finish"

    assert len(successes) == 1
    assert successes[0] in {"paused", "closed"}
    assert len(failures) == 1
    assert failures[0][0] == 409
    assert "Stale world lifecycle state" in failures[0][1]

    db_session.expire_all()
    persisted = db_session.query(models.World).filter_by(id=world_id).one()
    assert persisted.lifecycle_status == successes[0]
    assert (
        db_session.query(models.Log)
        .filter_by(user_id=user_id, action="world_lifecycle_transition")
        .count()
        == 1
    )
