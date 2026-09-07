import threading

import pytest
from fastapi import HTTPException

from app import models
from app.database import SessionLocal, engine
from app.services import anticheat

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="BM-0074 rate buckets require PostgreSQL row-lock validation",
)


def test_concurrent_rate_limit_cannot_be_bypassed(db_session, user):
    user_id = user.id
    barrier = threading.Barrier(2)
    successes: list[str] = []
    failures: list[int] = []
    result_lock = threading.Lock()

    def worker() -> None:
        session = SessionLocal()
        try:
            actor = session.query(models.User).filter_by(id=user_id).one()
            barrier.wait(timeout=5)
            anticheat.enforce_action_rate_limit(
                session,
                actor,
                "bm74.concurrent",
                limit=1,
                window_seconds=60,
            )
            with result_lock:
                successes.append("ok")
        except HTTPException as exc:
            session.rollback()
            with result_lock:
                failures.append(exc.status_code)
        finally:
            session.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent BM-0074 limiter did not finish"

    assert successes == ["ok"]
    assert failures == [429]

    db_session.expire_all()
    bucket = (
        db_session.query(models.AntiCheatRateBucket)
        .filter_by(user_id=user_id, action_key="bm74.concurrent")
        .one()
    )
    assert bucket.request_count == 1
    assert bucket.blocked_until is not None
    assert (
        db_session.query(models.AntiCheatFlag)
        .filter_by(
            user_id=user_id,
            type_of_violation="rate_limit:bm74.concurrent",
        )
        .count()
        == 1
    )
