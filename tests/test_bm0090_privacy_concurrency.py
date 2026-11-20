"""PostgreSQL parallel privacy requests must share one case ID."""

import threading

import pytest
from fastapi import Response
from sqlalchemy import select

from app import models
from app.database import SessionLocal, engine
from app.routers.account_data import PrivacyRequestCreate, create_privacy_request

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Requires PostgreSQL row locking and independent transactions",
)


@pytest.mark.parametrize("category", ["erasure", "rectification"])
def test_two_simultaneous_submissions_use_same_active_case(db_session, user, category):
    user_id = user.id
    gate = threading.Barrier(2)
    ids: list[int] = []
    failures: list[str] = []
    result_lock = threading.Lock()

    def worker() -> None:
        session = SessionLocal()
        try:
            actor = session.get(models.User, user_id)
            gate.wait(timeout=15)
            result = create_privacy_request(
                payload=PrivacyRequestCreate(kind=category),
                response=Response(),
                db=session,
                current_user=actor,
            )
            with result_lock:
                ids.append(result.id)
        except Exception as exc:
            session.rollback()
            with result_lock:
                failures.append(repr(exc))
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=25)
        assert not thread.is_alive(), "Concurrent privacy submissions hung"

    assert failures == []
    assert len(ids) == 2
    assert ids[0] == ids[1]
    db_session.expire_all()
    rows = db_session.scalars(
        select(models.SupportCase).where(
            models.SupportCase.requester_id == user_id,
            models.SupportCase.status.in_(("open", "in_progress")),
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].id == ids[0]
