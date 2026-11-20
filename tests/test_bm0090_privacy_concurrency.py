"""BM-0090: PostgreSQL exactly-once intake of a manual privacy case.

Run as part of the isolated PostgreSQL concurrency CI job. Do not implement
automatic account erasure or touch production data.
"""

import threading

import pytest
from fastapi import Response

from app import models
from app.database import SessionLocal, engine
from app.routers.account_data import PrivacyRequestCreate, create_privacy_request


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Privacy case deduplication relies on PostgreSQL row-level locks",
)


@pytest.mark.parametrize("kind", ["erasure", "rectification", "retention", "other"])
def test_concurrent_same_kind_submissions_create_one_active_case(db_session, user, kind):
    user_id = user.id
    barrier = threading.Barrier(2)
    mutex = threading.Lock()
    results = []
    errors = []

    def runner(detail):
        session = SessionLocal()
        try:
            actor = session.query(models.User).filter_by(id=user_id).one()
            barrier.wait(timeout=10)
            result = create_privacy_request(
                payload=PrivacyRequestCreate(kind=kind, details=detail),
                response=Response(),
                db=session,
                current_user=actor,
            )
            with mutex:
                results.append(result)
        except Exception as error:
            session.rollback()
            with mutex:
                errors.append(error)
        finally:
            session.close()

    threads = [
        threading.Thread(target=runner, args=("Concurrent request A",)),
        threading.Thread(target=runner, args=("Concurrent request B",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), "Concurrent privacy request hung"

    assert errors == [], [repr(error) for error in errors]
    assert len(results) == 2
    assert results[0].id == results[1].id
    assert results[0].kind == results[1].kind == kind
    assert results[0].status == results[1].status == "open"
    db_session.expire_all()
    cases = (
        db_session.query(models.SupportCase)
        .filter_by(requester_id=user_id)
        .all()
    )
    assert len(cases) == 1
    assert cases[0].id == results[0].id
    assert cases[0].subject.startswith("[PRIVACY]")
    # A repeated submission must not append a second person's free-text note.
    assert ("Concurrent request A" in cases[0].description) != (
        "Concurrent request B" in cases[0].description
    )


def test_concurrent_independent_accounts_are_isolated(db_session, user):
    opponent = models.User(
        username="bm90_concurrent_other",
        email="bm90_concurrent_other@example.com",
        hashed_password="test-only",
        is_verified=True,
    )
    db_session.add(opponent)
    db_session.commit()
    barrier = threading.Barrier(2)
    results = []
    errors = []
    mutex = threading.Lock()

    def runner(user_id):
        session = SessionLocal()
        try:
            actor = session.query(models.User).filter_by(id=user_id).one()
            barrier.wait(timeout=10)
            result = create_privacy_request(
                payload=PrivacyRequestCreate(kind="erasure"),
                response=Response(),
                db=session,
                current_user=actor,
            )
            with mutex:
                results.append((user_id, result.id))
        except Exception as error:
            session.rollback()
            with mutex:
                errors.append(error)
        finally:
            session.close()

    threads = [threading.Thread(target=runner, args=(uid,)) for uid in (user.id, opponent.id)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()

    assert errors == [], [repr(error) for error in errors]
    assert len(results) == 2
    assert results[0][1] != results[1][1]
    db_session.expire_all()
    for user_id, case_id in results:
        case = db_session.get(models.SupportCase, case_id)
        assert case.requester_id == user_id
        assert case.status == "open"
