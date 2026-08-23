import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import selectinload

from app import models
from app.database import SessionLocal, engine
from app.services import anticheat, combat
from app.services import movement as movement_service


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Movement concurrency guarantees require PostgreSQL row locks",
)


def _run_two(callback):
    barrier = threading.Barrier(2)
    results = []
    errors = []
    guard = threading.Lock()

    def runner():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            result = callback(session)
            with guard:
                results.append(result)
        except Exception as exc:
            session.rollback()
            with guard:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=runner) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent movement transaction did not finish"

    return results, errors


def test_two_dispatches_cannot_reserve_the_same_troops_twice(
    db_session, city, second_city, monkeypatch
):
    troop = models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=5)
    db_session.add(troop)
    db_session.commit()
    origin_id = city.id
    target_id = second_city.id

    monkeypatch.setattr(anticheat, "check_action_speed", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        anticheat,
        "check_movement_legitimacy",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        movement_service,
        "_run_dispatch_side_effects",
        lambda *args, **kwargs: None,
    )

    def dispatch_once(session):
        origin = (
            session.query(models.City)
            .options(selectinload(models.City.owner), selectinload(models.City.world))
            .filter_by(id=origin_id)
            .one()
        )
        target = session.query(models.City).filter_by(id=target_id).one()
        return movement_service.send_movement(
            session,
            origin,
            target_id,
            "reinforce",
            troops={"basic_infantry": 4},
            target_city=target,
        ).id

    results, errors = _run_two(dispatch_once)
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)

    db_session.expire_all()
    troop = (
        db_session.query(models.Troop)
        .filter_by(city_id=origin_id, unit_type="basic_infantry")
        .one()
    )
    assert troop.quantity == 1
    assert (
        db_session.query(models.Movement)
        .filter_by(origin_city_id=origin_id, movement_type="reinforce")
        .count()
        == 1
    )


def test_two_workers_resolve_one_attack_exactly_once(db_session, city, monkeypatch):
    barbarian = models.City(
        name="Concurrent Barbarian",
        owner_id=None,
        world_id=city.world_id,
        x=8,
        y=0,
        wood=120.0,
        stone=120.0,
        iron=120.0,
        gold=120.0,
    )
    attack = models.Movement(
        origin_city_id=city.id,
        target_city=barbarian,
        world_id=city.world_id,
        movement_type="attack",
        troops={"basic_infantry": 3},
        resources={},
        spy_count=0,
        arrival_time=datetime.now(timezone.utc) - timedelta(seconds=1),
        speed_used=1.0,
        status="ongoing",
    )
    db_session.add_all([barbarian, attack])
    db_session.commit()
    attack_id = attack.id
    barbarian_id = barbarian.id

    monkeypatch.setattr(combat, "_luck", lambda: 0.0)
    monkeypatch.setattr(
        movement_service,
        "_run_resolution_effect",
        lambda *args, **kwargs: None,
    )

    def resolve_once(session):
        return len(movement_service.resolve_due_movements(session))

    results, errors = _run_two(resolve_once)
    assert errors == []
    assert sorted(results) == [0, 1]

    db_session.expire_all()
    completed = db_session.query(models.Movement).filter_by(id=attack_id).one()
    assert completed.status == "completed"
    assert (
        db_session.query(models.Report)
        .filter_by(attacker_city_id=city.id, defender_city_id=barbarian_id)
        .count()
        == 2
    )
    assert (
        db_session.query(models.Movement)
        .filter_by(target_city_id=city.id, movement_type="return", status="ongoing")
        .count()
        == 1
    )

    refreshed_barbarian = db_session.query(models.City).filter_by(id=barbarian_id).one()
    first_balances = (
        refreshed_barbarian.wood,
        refreshed_barbarian.stone,
        refreshed_barbarian.iron,
        refreshed_barbarian.gold,
    )
    movement_service.resolve_due_movements(db_session)
    db_session.expire_all()
    refreshed_barbarian = db_session.query(models.City).filter_by(id=barbarian_id).one()
    assert (
        refreshed_barbarian.wood,
        refreshed_barbarian.stone,
        refreshed_barbarian.iron,
        refreshed_barbarian.gold,
    ) == pytest.approx(first_balances)
