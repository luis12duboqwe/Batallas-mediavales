import threading

import pytest
from fastapi import HTTPException

from app import models
from app.database import SessionLocal, engine
from app.services import admin as admin_service

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="BM-0073 reversal serialization requires PostgreSQL row locks",
)


def test_concurrent_reversal_applies_exactly_once(db_session, city):
    operator = models.User(
        username="bm73_concurrent_operator",
        email="bm73-concurrent-operator@example.com",
        hashed_password="placeholder",
        is_verified=True,
        is_admin=True,
        admin_role="operator",
    )
    db_session.add(operator)
    db_session.commit()
    db_session.refresh(operator)

    original_wood = city.wood
    admin_service.update_city_resources(
        db_session,
        city.id,
        {"wood": original_wood + 321},
        operator,
        reason="Create reversible concurrent test correction",
    )
    original_log = (
        db_session.query(models.Log)
        .filter_by(action="update_city_resources", target_id=city.id)
        .order_by(models.Log.id.desc())
        .first()
    )
    assert original_log is not None
    log_id = original_log.id
    operator_id = operator.id

    barrier = threading.Barrier(2)
    successes: list[int] = []
    failures: list[tuple[int, str]] = []
    result_lock = threading.Lock()

    def worker() -> None:
        session = SessionLocal()
        try:
            actor = session.query(models.User).filter_by(id=operator_id).one()
            barrier.wait(timeout=5)
            reversal = admin_service.revert_action(
                session,
                log_id,
                admin_user=actor,
                reason="Concurrent exact-once reversal",
            )
            with result_lock:
                successes.append(reversal.id)
        except HTTPException as exc:
            session.rollback()
            with result_lock:
                failures.append((exc.status_code, str(exc.detail)))
        finally:
            session.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent BM-0073 reversal did not finish"

    assert len(successes) == 1
    assert failures == [(409, "Audit action already reverted")]

    db_session.expire_all()
    persisted_city = db_session.query(models.City).filter_by(id=city.id).one()
    persisted_log = db_session.query(models.Log).filter_by(id=log_id).one()
    assert persisted_city.wood == original_wood
    assert persisted_log.reversed_at is not None
    assert persisted_log.reversed_by_id == operator_id
    assert (
        db_session.query(models.Log)
        .filter_by(action="revert_admin_action", target_id=city.id)
        .count()
        == 1
    )
