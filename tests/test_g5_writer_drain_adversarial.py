"""G5/#183 adversarial evidence for writer draining; disposable in-process doubles.

These tests intentionally do NOT certify a write barrier. They demonstrate
what the current scheduler/HTTP surfaces can still write after an edge 503.
"""
from contextlib import contextmanager
from pathlib import Path
import ast
import signal
import threading

import pytest

from app import scheduler as scheduler_module
from app import worker as worker_module


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


@contextmanager
def admitted_job(_name):
    yield True


def test_worker_sigterm_waits_for_graceful_shutdown_of_inflight_job(monkeypatch):
    """An in-flight job blocks shutdown until its controlled completion."""
    handlers = {}
    started = threading.Event()
    release_job = threading.Event()
    worker_finished = threading.Event()
    shutdown_called = threading.Event()
    job_thread = []

    def register(signum, handler):
        handlers[signum] = handler

    def run_job():
        started.set()
        assert release_job.wait(timeout=4)

    def start():
        t = threading.Thread(target=run_job, daemon=True)
        job_thread.append(t)
        t.start()

    def stop():
        shutdown_called.set()
        for t in job_thread:
            t.join(timeout=4)
            assert not t.is_alive()

    def run_worker():
        try:
            worker_module.main()
        finally:
            worker_finished.set()

    monkeypatch.setattr(worker_module, "_shutdown_requested", threading.Event())
    monkeypatch.setattr(worker_module.signal, "signal", register)
    monkeypatch.setattr(worker_module, "start_scheduler", start)
    monkeypatch.setattr(worker_module, "shutdown_scheduler", stop)

    process = threading.Thread(target=run_worker, daemon=True)
    process.start()
    try:
        assert started.wait(timeout=3)
        assert signal.SIGTERM in handlers and signal.SIGINT in handlers
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        assert shutdown_called.wait(timeout=3)
        assert not worker_finished.is_set(), "Worker exited while a job was still in-flight"
    finally:
        release_job.set()
        worker_module._shutdown_requested.set()
        process.join(timeout=5)
    assert worker_finished.is_set()
    assert not process.is_alive()


def test_current_worker_can_commit_after_sigterm_without_global_barrier(monkeypatch):
    """REPRODUCTION of missing write admission guard, not a passing RPO=0 claim."""
    session = FakeSession()
    entered = threading.Event()
    release = threading.Event()
    complete = threading.Event()
    errors = []

    def callback(_db):
        entered.set()
        assert release.wait(timeout=4)

    def run():
        try:
            assert scheduler_module._run_database_job("queue_processing", callback)
        except BaseException as exc:
            errors.append(exc)
        finally:
            complete.set()

    monkeypatch.setattr(scheduler_module, "distributed_job_lock", admitted_job)
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(worker_module, "_shutdown_requested", threading.Event())

    job = threading.Thread(target=run, daemon=True)
    job.start()
    try:
        assert entered.wait(timeout=3)
        worker_module._request_shutdown(signal.SIGTERM, None)
        assert worker_module._shutdown_requested.is_set()
        assert session.commits == 0
    finally:
        release.set()
        job.join(timeout=5)
    assert complete.is_set()
    assert errors == []
    # A transaction can commit after a signal; stopping HTTP at Nginx alone
    # does not protect a database backup or prevent this worker from writing.
    assert session.commits == 1
    assert session.rollbacks == 0
    assert session.closes == 1


def test_database_job_rolls_back_and_closes_on_failure(monkeypatch):
    """The exception path must not accidentally commit while the gate is added."""
    session = FakeSession()

    def fail(_db):
        raise RuntimeError("synthetic, no real DB")

    monkeypatch.setattr(scheduler_module, "distributed_job_lock", admitted_job)
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: session)
    assert scheduler_module._run_database_job("barbarian_ai", fail) is False
    assert (session.commits, session.rollbacks, session.closes) == (0, 1, 1)


def test_job_lock_rejection_never_creates_write_session(monkeypatch):
    @contextmanager
    def denied(_name):
        yield False

    monkeypatch.setattr(scheduler_module, "distributed_job_lock", denied)
    monkeypatch.setattr(
        scheduler_module, "SessionLocal",
        lambda: pytest.fail("Rejected job must never open an ORM session"),
    )
    assert scheduler_module._run_database_job("queue_processing", lambda db: None) is False


def test_scheduler_job_locks_are_not_a_global_writer_barrier():
    """Distinct keys deliberately coexist; they cannot serialize a G5 cutover."""
    with scheduler_module.distributed_job_lock("queue_processing") as queue:
        with scheduler_module.distributed_job_lock("barbarian_ai") as barbarian:
            assert queue is True and barbarian is True


def test_worker_shutdown_calls_wait_true_but_has_no_bounded_deadline(monkeypatch):
    calls = []

    class FakeScheduler:
        running = True

        def shutdown(self, *, wait):
            calls.append(wait)

    monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())
    scheduler_module.shutdown_scheduler()
    assert calls == [True]  # Waiting is necessary, but not sufficient for G5.


def test_exact_active_worker_triggers_are_in_writer_inventory(monkeypatch):
    captures = []

    class FakeScheduler:
        running = False

        def add_job(self, callback, *, trigger, id, **kwargs):
            captures.append((id, int(trigger.interval.total_seconds()), callback))

        def start(self):
            captures.append(("started", 0, None))

    monkeypatch.setattr(scheduler_module, "scheduler", FakeScheduler())
    scheduler_module.start_scheduler()
    assert {(name, interval) for name, interval, _ in captures if name != "started"} == {
        ("barbarian_ai", 300), ("queue_processing", 5)
    }
    assert captures[-1][0] == "started"


def test_get_message_is_a_writer_even_though_http_method_is_safe():
    """GET /message/{id} marks read status; edge drain must block all methods."""
    path = (Path(__file__).resolve().parents[1] /
            "batalla_medieval_backend/app/routers/message.py")
    module = ast.parse(path.read_text(encoding="utf-8"))
    fn = next(node for node in module.body
              if isinstance(node, ast.FunctionDef) and node.name == "read_message")
    assert any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit"
        for node in ast.walk(fn)
    ), "Re-evaluate writer inventory if GET /message/{id} stops committing"


def test_scheduler_does_not_register_work_on_web_app_startup():
    """Backend and workers must be counted separately; no scheduler in HTTP."""
    from app.main import app

    names = {handler.__name__ for handler in app.router.on_startup}
    assert "start_scheduler" not in names


def test_shutdown_is_not_a_substitute_for_cutover_state_machine():
    """Explicitly record missing durable transaction fence as an open P1."""
    # A scheduler can finish a database commit after SIGTERM (above).
    # Do not add a fake 'barrier complete' assertion to these tests.
    assert "COMMITTED_WRITERS_ALLOWED" not in scheduler_module.__dict__
