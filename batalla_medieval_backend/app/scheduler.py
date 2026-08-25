"""Background jobs executed by the dedicated game worker.

The HTTP process must never start this scheduler. Production workers coordinate
through PostgreSQL advisory locks so that only one process executes a given
periodic job at a time, even when multiple worker replicas are running.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from .database import SessionLocal, engine
from .services import barbarian_ai, pve_rules, queue as queue_service

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")

# Stable signed 64-bit keys reserved for Batallas Medievales background jobs.
_JOB_LOCK_KEYS = {
    "barbarian_ai": 42130001,
    "queue_processing": 42130002,
}
_LOCAL_LOCKS = {name: Lock() for name in _JOB_LOCK_KEYS}


@contextmanager
def distributed_job_lock(job_name: str) -> Iterator[bool]:
    """Yield whether this process acquired the singleton lock for ``job_name``.

    PostgreSQL uses a session-level advisory lock held on a dedicated
    connection. Keeping that connection separate from the job's ORM session is
    important because queue services may commit while the job is running.
    SQLite (development/tests) falls back to an in-process non-blocking lock.
    """

    if job_name not in _JOB_LOCK_KEYS:
        raise ValueError(f"Unknown scheduled job: {job_name}")

    if engine.dialect.name != "postgresql":
        lock = _LOCAL_LOCKS[job_name]
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()
        return

    connection = engine.connect()
    acquired = False
    key = _JOB_LOCK_KEYS[job_name]
    try:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": key},
            ).scalar()
        )
        yield acquired
    finally:
        if acquired:
            try:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": key},
                )
            except Exception:
                logger.exception("Failed to release advisory lock for %s", job_name)
        connection.close()


def _run_database_job(job_name: str, callback) -> bool:
    """Run a database job once if this worker owns its distributed lock."""

    with distributed_job_lock(job_name) as acquired:
        if not acquired:
            logger.debug("Skipping %s because another worker owns the lock", job_name)
            return False

        db = SessionLocal()
        try:
            callback(db)
            db.commit()
            return True
        except Exception:
            db.rollback()
            logger.exception("Scheduled job failed: %s", job_name)
            return False
        finally:
            db.close()


def run_barbarian_ai_job() -> bool:
    """Run one durable PvE tick exactly once across active worker replicas."""

    return _run_database_job("barbarian_ai", barbarian_ai.process_barbarian_growth)


def run_queue_processing_job() -> bool:
    """Process due building, troop and movement queues once per interval."""

    return _run_database_job("queue_processing", queue_service.process_all_queues)


def start_scheduler() -> None:
    """Configure and start the worker scheduler once in this process."""

    if scheduler.running:
        return

    scheduler.add_job(
        run_barbarian_ai_job,
        trigger=IntervalTrigger(seconds=pve_rules.PVE_TICK_SECONDS),
        id="barbarian_ai",
        name="Versioned PvE Tick",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        run_queue_processing_job,
        trigger=IntervalTrigger(seconds=5),
        id="queue_processing",
        name="Queue Processing",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=15,
    )

    scheduler.start()
    logger.info("Dedicated game scheduler started")


def shutdown_scheduler() -> None:
    """Stop the scheduler without waiting for the process to be killed."""

    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Dedicated game scheduler stopped")
