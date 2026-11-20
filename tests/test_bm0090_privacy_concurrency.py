"""BM-0090: deterministic PostgreSQL row-lock contention for privacy intake.

The same-account test holds the user row lock until BOTH submissions are
observed waiting on PostgreSQL lock events. Removing FOR UPDATE from the
handler causes this test to fail, even if one request happens to finish first.
"""

import threading
import time

import pytest
from fastapi import Response
from sqlalchemy import event, text

from app import models
from app.database import SessionLocal, engine
from app.routers.account_data import PrivacyRequestCreate, create_privacy_request


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Privacy deduplication relies on PostgreSQL row-level locks",
)


def _racing_requests(user_ids, kind, *, require_contention):
    """Use distinct DB connections, bounded statement waits and reliable teardown."""
    participant_count = len(user_ids)
    barrier = threading.Barrier(participant_count)
    mutex = threading.Lock()
    results = []
    errors = []
    pids = []
    threads = []
    blocker = SessionLocal()
    monitor = SessionLocal()
    contention_seen = False

    def worker(user_id, details):
        session = SessionLocal()
        try:
            # SET LOCAL is scoped to this worker's transaction and protects CI
            # against a permanently blocked PostgreSQL statement.
            session.execute(text("SET LOCAL lock_timeout = '10000ms'"))
            session.execute(text("SET LOCAL statement_timeout = '12000ms'"))
            actor = session.query(models.User).filter_by(id=user_id).one()
            backend_pid = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
            with mutex:
                pids.append(backend_pid)
            barrier.wait(timeout=8)
            result = create_privacy_request(
                payload=PrivacyRequestCreate(kind=kind, details=details),
                response=Response(),
                db=session,
                current_user=actor,
            )
            with mutex:
                results.append((user_id, result))
        except Exception as exc:
            session.rollback()
            with mutex:
                errors.append(exc)
        finally:
            session.close()

    try:
        if require_contention:
            # NO KEY UPDATE blocks the handler's FOR UPDATE but permits the
            # KEY SHARE validation of the SupportCase.requester_id foreign key.
            # Otherwise an INSERT could impersonate a handler row-lock wait.
            blocker.execute(
                text("SELECT id FROM users WHERE id = :id FOR NO KEY UPDATE"),
                {"id": user_ids[0]},
            ).one()
        threads = [
            threading.Thread(
                target=worker,
                args=(user_id, f"Concurrent request {index}"),
                daemon=True,
            )
            for index, user_id in enumerate(user_ids)
        ]
        for thread in threads:
            thread.start()

        if require_contention:
            # PostgreSQL exposes its own lock waits for both connections.
            # This is a deterministic negative control: if the handler's
            # FOR UPDATE is removed, neither worker waits and we fail.
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                with mutex:
                    current_pids = list(pids)
                if len(current_pids) == participant_count:
                    waiting = monitor.execute(
                        text("""
                            SELECT count(*)
                            FROM pg_stat_activity
                            WHERE pid IN (:pid_a, :pid_b)
                              AND wait_event_type = 'Lock'
                              AND state = 'active'
                              AND query LIKE 'SELECT users.%'
                        """),
                        {"pid_a": current_pids[0], "pid_b": current_pids[1]},
                    ).scalar_one()
                    # PostgreSQL caches activity snapshots within a transaction.
                    # Roll back after every probe to observe newly waiting workers.
                    monitor.rollback()
                    if waiting == participant_count:
                        contention_seen = True
                        break
                time.sleep(0.04)
    finally:
        # Always release the blocker and cancel any overlong statement;
        # a failed assertion must never strand a CI worker or later drop_all().
        blocker.rollback()
        blocker.close()
        for thread in threads:
            thread.join(timeout=13)
        alive = [thread for thread in threads if thread.is_alive()]
        if alive:
            with mutex:
                current_pids = list(pids)
            for pid in current_pids:
                monitor.execute(text("SELECT pg_cancel_backend(:pid)"), {"pid": pid})
            monitor.commit()
            for thread in alive:
                thread.join(timeout=5)
        monitor.close()

    assert all(not thread.is_alive() for thread in threads), (
        "PostgreSQL privacy request workers did not terminate after cancellation"
    )
    assert not errors, [repr(error) for error in errors]
    if require_contention:
        assert contention_seen, (
            "Both requests did not block on the same PostgreSQL row; "
            "removing the handler FOR UPDATE must fail this regression"
        )
    return results


@pytest.mark.parametrize("kind", ["erasure", "rectification", "retention", "other"])
def test_concurrent_same_kind_submissions_create_one_active_case(db_session, user, kind):
    results = _racing_requests([user.id, user.id], kind, require_contention=True)
    assert len(results) == 2
    assert results[0][1].id == results[1][1].id
    assert results[0][1].kind == results[1][1].kind == kind
    assert results[0][1].status == results[1][1].status == "open"

    db_session.expire_all()
    cases = db_session.query(models.SupportCase).filter_by(requester_id=user.id).all()
    assert len(cases) == 1
    assert cases[0].id == results[0][1].id
    assert cases[0].subject.startswith("[PRIVACY]")
    # The second concurrent request cannot overwrite the first request's note.
    assert ("Concurrent request 0" in cases[0].description) != (
        "Concurrent request 1" in cases[0].description
    )


def test_concurrent_independent_accounts_remain_isolated(db_session, user):
    other = models.User(
        username="bm90_concurrent_other",
        email="bm90_concurrent_other@example.com",
        hashed_password="test-only",
        is_verified=True,
    )
    db_session.add(other)
    db_session.commit()
    results = _racing_requests([user.id, other.id], "erasure", require_contention=False)
    assert len(results) == 2
    assert results[0][1].id != results[1][1].id

    db_session.expire_all()
    for user_id, case in results:
        persisted = db_session.get(models.SupportCase, case.id)
        assert persisted.requester_id == user_id
        assert persisted.status == "open"


def test_removed_handler_lock_fails_the_contention_gate(db_session, user):
    """Negative control: simulate a handler missing FOR UPDATE, not an FK wait."""
    rewritten = []

    def remove_handler_lock(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("SELECT users.") and " FOR UPDATE" in statement:
            rewritten.append(1)
            return statement.replace(" FOR UPDATE", ""), parameters
        return statement, parameters

    event.listen(engine, "before_cursor_execute", remove_handler_lock, retval=True)
    try:
        with pytest.raises(AssertionError, match="Both requests did not block"):
            _racing_requests([user.id, user.id], "erasure", require_contention=True)
    finally:
        event.remove(engine, "before_cursor_execute", remove_handler_lock)

    assert len(rewritten) == 2, "Negative control did not remove both handler row locks"
    db_session.expire_all()
    assert db_session.query(models.SupportCase).filter_by(requester_id=user.id).count() == 1
