import threading
import time

import pytest
from fastapi import HTTPException

from app import models
from app.database import SessionLocal, engine
from app.services import adventure, hero, world_lifecycle
from app.utils import utc_now

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


def test_pause_waits_for_inflight_world_clock_row_lock(db_session, user, city):
    user.is_admin = True
    world = city.world
    world.lifecycle_status = "open"
    world.is_active = True
    movement = models.Movement(
        origin_city_id=city.id,
        target_city_id=city.id,
        world_id=world.id,
        movement_type="return",
        troops={},
        resources={},
        arrival_time=city.last_production,
        status="ongoing",
    )
    db_session.add(movement)
    db_session.commit()
    world_id = world.id
    user_id = user.id
    movement_id = movement.id

    locked = threading.Event()
    release = threading.Event()
    pause_started = threading.Event()
    pause_done = threading.Event()
    errors: list[str] = []

    def hold_worker_row() -> None:
        session = SessionLocal()
        try:
            (
                session.query(models.Movement)
                .filter(models.Movement.id == movement_id)
                .with_for_update()
                .one()
            )
            locked.set()
            assert release.wait(timeout=5), "Timed out waiting to release worker row"
            session.commit()
        except Exception as exc:
            session.rollback()
            errors.append(f"holder: {exc}")
        finally:
            session.close()

    def pause_world() -> None:
        session = SessionLocal()
        try:
            admin_user = session.query(models.User).filter_by(id=user_id).one()
            pause_started.set()
            world_lifecycle.transition_world(
                session,
                world_id,
                target_status="paused",
                expected_status="open",
                reason="BM-0072 worker barrier regression",
                admin_user=admin_user,
            )
            pause_done.set()
        except Exception as exc:
            session.rollback()
            errors.append(f"pause: {exc}")
        finally:
            session.close()

    holder = threading.Thread(target=hold_worker_row)
    holder.start()
    assert locked.wait(timeout=5), "Worker row was not locked"

    pauser = threading.Thread(target=pause_world)
    pauser.start()
    assert pause_started.wait(timeout=5), "Pause transition did not start"
    time.sleep(0.2)
    assert not pause_done.is_set(), "Pause committed while worker still owned a clock row"

    released_at = utc_now()
    release.set()
    holder.join(timeout=10)
    pauser.join(timeout=10)
    assert not holder.is_alive()
    assert not pauser.is_alive()
    assert errors == []
    assert pause_done.is_set()

    db_session.expire_all()
    persisted = db_session.query(models.World).filter_by(id=world_id).one()
    assert persisted.lifecycle_status == "paused"
    pause_started_at = persisted.pause_started_at
    if pause_started_at.tzinfo is None:
        pause_started_at = pause_started_at.replace(tzinfo=released_at.tzinfo)
    assert pause_started_at >= released_at


def test_adventure_mutation_waits_for_world_lock_and_loses_to_pause(
    db_session, user, city
):
    city.world.lifecycle_status = "open"
    city.world.is_active = True
    db_session.commit()

    hero_obj = hero.get_hero(db_session, user.id, city.world_id)
    adv = adventure.get_adventures(db_session, hero_obj.id)[0]
    world_id = city.world_id
    adventure_id = adv.id
    hero_id = hero_obj.id

    world_locked = threading.Event()
    allow_pause_commit = threading.Event()
    mutation_started = threading.Event()
    mutation_done = threading.Event()
    mutation_errors: list[str] = []

    def pause_holder() -> None:
        session = SessionLocal()
        try:
            world = (
                session.query(models.World)
                .filter(models.World.id == world_id)
                .with_for_update()
                .one()
            )
            world.lifecycle_status = "paused"
            world.is_active = False
            world.pause_started_at = utc_now()
            world_locked.set()
            assert allow_pause_commit.wait(timeout=5)
            session.commit()
        finally:
            session.close()

    def start_mutation() -> None:
        session = SessionLocal()
        try:
            local_hero = session.query(models.Hero).filter_by(id=hero_id).one()
            mutation_started.set()
            adventure.start_adventure(session, adventure_id, local_hero)
        except Exception as exc:
            session.rollback()
            mutation_errors.append(str(exc))
        finally:
            mutation_done.set()
            session.close()

    pauser = threading.Thread(target=pause_holder)
    pauser.start()
    assert world_locked.wait(timeout=5)

    mutator = threading.Thread(target=start_mutation)
    mutator.start()
    assert mutation_started.wait(timeout=5)
    time.sleep(0.2)
    assert not mutation_done.is_set(), "Adventure bypassed the lifecycle row lock"

    allow_pause_commit.set()
    pauser.join(timeout=10)
    mutator.join(timeout=10)
    assert not pauser.is_alive()
    assert not mutator.is_alive()
    assert mutation_errors == ["World is not open"]

    db_session.expire_all()
    persisted = db_session.query(models.Adventure).filter_by(id=adventure_id).one()
    assert persisted.status == "available"
