from contextlib import contextmanager
from datetime import timedelta

from app import models
from app import scheduler as scheduler_module
from app.main import app
from app.services import troops as troop_service
from app.utils import utc_now


def test_local_job_lock_prevents_overlapping_queue_runs():
    """The SQLite/test fallback must reject a second overlapping runner."""

    with scheduler_module.distributed_job_lock("queue_processing") as first:
        assert first is True
        with scheduler_module.distributed_job_lock("queue_processing") as second:
            assert second is False


def test_queue_job_does_not_open_session_when_lock_is_busy(monkeypatch):
    """A worker that loses the distributed lock must not process any queues."""

    @contextmanager
    def denied_lock(_job_name):
        yield False

    def unexpected_session():
        raise AssertionError("SessionLocal must not be called without the job lock")

    monkeypatch.setattr(scheduler_module, "distributed_job_lock", denied_lock)
    monkeypatch.setattr(scheduler_module, "SessionLocal", unexpected_session)

    assert scheduler_module.run_queue_processing_job() is False


def test_api_startup_does_not_register_scheduler_callbacks():
    """Scaling the HTTP app must not create additional periodic schedulers."""

    startup_handlers = {
        f"{handler.__module__}.{handler.__name__}" for handler in app.router.on_startup
    }
    shutdown_handlers = {
        f"{handler.__module__}.{handler.__name__}" for handler in app.router.on_shutdown
    }

    assert "app.scheduler.start_scheduler" not in startup_handlers
    assert "app.scheduler.shutdown_scheduler" not in shutdown_handlers


def test_completed_troop_queue_is_idempotent_on_retry(db_session, city):
    """A successful queue cannot add the same troops twice on a later retry."""

    queue_entry = models.TroopQueue(
        city_id=city.id,
        troop_type="basic_infantry",
        amount=4,
        finish_time=utc_now() - timedelta(seconds=1),
    )
    db_session.add(queue_entry)
    db_session.commit()

    first = troop_service.process_troop_queues(db_session)
    second = troop_service.process_troop_queues(db_session)

    trained = (
        db_session.query(models.Troop)
        .filter(
            models.Troop.city_id == city.id,
            models.Troop.unit_type == "basic_infantry",
        )
        .one()
    )

    assert len(first) == 1
    assert second == []
    assert trained.quantity == 4
