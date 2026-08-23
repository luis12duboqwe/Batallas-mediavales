import threading
from datetime import timedelta

import pytest

from app import models, schemas
from app.database import SessionLocal, engine
from app.services import market
from app.services import movement as movement_service
from app.utils import utc_now


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="G3 24h simulation requires PostgreSQL row locks and SKIP LOCKED",
)

HOURS = 24
TRANSFER_PER_HOUR = 5


def _run_parallel(callbacks):
    barrier = threading.Barrier(len(callbacks))
    results = [None] * len(callbacks)

    def runner(index, callback):
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            results[index] = callback(session)
        except Exception as exc:
            session.rollback()
            results[index] = exc
        finally:
            session.close()

    threads = [
        threading.Thread(target=runner, args=(index, callback))
        for index, callback in enumerate(callbacks)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive(), "G3 concurrent operation did not finish"
    return results


def _create_peer(db_session, world_id: int):
    peer = models.User(
        username="g3_peer",
        email="g3_peer@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(peer)
    db_session.flush()
    city = models.City(
        name="G3 Peer Capital",
        owner_id=peer.id,
        world_id=world_id,
        x=60,
        y=60,
        wood=1000,
        stone=1000,
        iron=1000,
        gold=1000,
        last_production=utc_now(),
    )
    db_session.add(city)
    db_session.flush()
    db_session.add(models.Building(city_id=city.id, name="market", level=1))
    db_session.commit()
    db_session.refresh(city)
    return city


def _dispatch(origin_id: int, target_id: int, *, resource: str):
    def callback(session):
        origin = session.query(models.City).filter(models.City.id == origin_id).one()
        payload = {"target_city_id": target_id, "wood": 0, "stone": 0, "iron": 0, "gold": 0}
        payload[resource] = TRANSFER_PER_HOUR
        movement = market.send_resources(
            session,
            origin,
            schemas.TransportRequest(**payload),
        )
        return movement.id

    return callback


def _worker(session):
    return [movement.id for movement in movement_service.resolve_due_movements(session)]


def _force_due(db_session, movement_type: str):
    due_ids = [
        movement_id
        for (movement_id,) in (
            db_session.query(models.Movement.id)
            .filter(
                models.Movement.movement_type == movement_type,
                models.Movement.status == "ongoing",
            )
            .order_by(models.Movement.id.asc())
            .all()
        )
    ]
    if due_ids:
        (
            db_session.query(models.Movement)
            .filter(models.Movement.id.in_(due_ids))
            .update(
                {models.Movement.arrival_time: utc_now() - timedelta(seconds=1)},
                synchronize_session=False,
            )
        )
        db_session.commit()
    return due_ids


def _resolve_with_two_workers(expected_ids):
    results = _run_parallel([_worker, _worker])
    for result in results:
        assert not isinstance(result, Exception), repr(result)
    resolved_ids = [movement_id for batch in results for movement_id in batch]
    assert sorted(resolved_ids) == sorted(expected_ids)
    assert len(resolved_ids) == len(set(resolved_ids)), "A movement was resolved twice"


def test_g3_concurrent_24h_transport_simulation_has_no_duplicates_or_negative_stock(
    db_session,
    city,
    monkeypatch,
):
    # Keep this gate focused on durable economic/worker invariants, not telemetry.
    monkeypatch.setattr(market, "_audit_transport_after_commit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        market.production,
        "record_resource_gains",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        movement_service,
        "_run_resolution_effect",
        lambda *args, **kwargs: None,
    )

    city.wood = city.stone = city.iron = city.gold = 1000
    city.last_production = utc_now()
    db_session.add(models.Building(city_id=city.id, name="market", level=1))
    db_session.commit()
    peer_city = _create_peer(db_session, city.world_id)

    dispatched_ids = []
    for _hour in range(HOURS):
        dispatch_results = _run_parallel(
            [
                _dispatch(city.id, peer_city.id, resource="stone"),
                _dispatch(peer_city.id, city.id, resource="gold"),
            ]
        )
        for result in dispatch_results:
            assert not isinstance(result, Exception), repr(result)
        assert len(set(dispatch_results)) == 2
        dispatched_ids.extend(dispatch_results)

        outgoing_due = _force_due(db_session, "transport")
        assert sorted(outgoing_due) == sorted(dispatch_results)
        _resolve_with_two_workers(outgoing_due)

        return_due = _force_due(db_session, "transport_return")
        assert len(return_due) == 2
        _resolve_with_two_workers(return_due)

        db_session.expire_all()
        balances = (
            db_session.query(models.City)
            .filter(models.City.id.in_([city.id, peer_city.id]))
            .all()
        )
        assert len(balances) == 2
        for current in balances:
            assert current.wood >= 0
            assert current.stone >= 0
            assert current.iron >= 0
            assert current.gold >= 0
        assert (
            db_session.query(models.Movement)
            .filter(models.Movement.status == "ongoing")
            .count()
            == 0
        )

    db_session.expire_all()
    transports = (
        db_session.query(models.Movement)
        .filter(models.Movement.movement_type == "transport")
        .all()
    )
    returns = (
        db_session.query(models.Movement)
        .filter(models.Movement.movement_type == "transport_return")
        .all()
    )

    assert len(dispatched_ids) == HOURS * 2
    assert len(set(dispatched_ids)) == HOURS * 2
    assert len(transports) == HOURS * 2
    assert len(returns) == HOURS * 2
    assert all(movement.status == "completed" for movement in transports + returns)
