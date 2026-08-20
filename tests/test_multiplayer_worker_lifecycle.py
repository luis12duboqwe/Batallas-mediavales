from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.services import combat, espionage
from app.services import movement as movement_service


FIXED_NOW = datetime(2026, 8, 20, 20, 0, tzinfo=timezone.utc)


def _peer_city(db_session, world_id: int, *, username: str, x: int, y: int):
    peer = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
        protection_ends_at=FIXED_NOW - timedelta(hours=1),
    )
    db_session.add(peer)
    db_session.flush()
    target = models.City(
        name=f"Capital {username}",
        owner_id=peer.id,
        world_id=world_id,
        x=x,
        y=y,
        wood=500.0,
        clay=500.0,
        iron=500.0,
        last_production=FIXED_NOW,
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(peer)
    db_session.refresh(target)
    return peer, target


def _due_movement(db_session, *, origin, target, movement_type, troops=None, resources=None, spy_count=0):
    movement = models.Movement(
        origin_city_id=origin.id,
        target_city_id=target.id,
        world_id=origin.world_id,
        movement_type=movement_type,
        troops=troops or {},
        resources=resources or {},
        spy_count=spy_count,
        arrival_time=FIXED_NOW - timedelta(seconds=1),
        speed_used=1.0,
        status="ongoing",
    )
    db_session.add(movement)
    db_session.commit()
    db_session.refresh(movement)
    return movement


def _disable_resolution_side_effects(monkeypatch):
    monkeypatch.setattr(movement_service, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(
        movement_service,
        "_run_resolution_effect",
        lambda *args, **kwargs: None,
    )


def test_two_player_attack_resolves_reports_and_returns_without_conquest(
    db_session,
    city,
    monkeypatch,
):
    peer, target = _peer_city(
        db_session,
        city.world_id,
        username="worker_defender",
        x=30,
        y=30,
    )
    city.wood = city.clay = city.iron = 1000.0
    city.last_production = FIXED_NOW
    db_session.add(city)
    db_session.commit()

    _disable_resolution_side_effects(monkeypatch)
    monkeypatch.setattr(combat, "_luck", lambda: 0.0)

    outgoing = _due_movement(
        db_session,
        origin=city,
        target=target,
        movement_type="attack",
        troops={"basic_infantry": 2},
    )

    resolved = movement_service.resolve_due_movements(db_session)
    assert [item.id for item in resolved] == [outgoing.id]

    db_session.expire_all()
    target_after = db_session.query(models.City).filter_by(id=target.id).one()
    assert target_after.owner_id == peer.id
    assert db_session.query(models.Report).filter_by(report_type="battle").count() == 2

    return_move = (
        db_session.query(models.Movement)
        .filter_by(target_city_id=city.id, movement_type="return", status="ongoing")
        .one()
    )
    assert return_move.world_id == city.world_id
    assert return_move.troops.get("basic_infantry", 0) > 0

    return_move.arrival_time = FIXED_NOW - timedelta(seconds=1)
    db_session.add(return_move)
    db_session.commit()
    movement_service.resolve_due_movements(db_session)

    db_session.expire_all()
    returned = (
        db_session.query(models.Troop)
        .filter_by(city_id=city.id, unit_type="basic_infantry")
        .one()
    )
    assert returned.quantity == return_move.troops["basic_infantry"]


def test_two_player_spy_success_creates_reports_and_returns_surviving_spies(
    db_session,
    city,
    monkeypatch,
):
    _, target = _peer_city(
        db_session,
        city.world_id,
        username="worker_spy_target",
        x=31,
        y=31,
    )
    _disable_resolution_side_effects(monkeypatch)
    monkeypatch.setattr(espionage.random, "random", lambda: 0.0)

    outgoing = _due_movement(
        db_session,
        origin=city,
        target=target,
        movement_type="spy",
        spy_count=2,
    )
    movement_service.resolve_due_movements(db_session)

    db_session.expire_all()
    assert db_session.query(models.Report).filter_by(report_type="spy").count() == 2
    return_move = (
        db_session.query(models.Movement)
        .filter_by(target_city_id=city.id, movement_type="return", status="ongoing")
        .one()
    )
    assert return_move.troops == {"spy": 2}

    return_move.arrival_time = FIXED_NOW - timedelta(seconds=1)
    db_session.add(return_move)
    db_session.commit()
    movement_service.resolve_due_movements(db_session)

    db_session.expire_all()
    spies = (
        db_session.query(models.Troop)
        .filter_by(city_id=city.id, unit_type="spy")
        .one()
    )
    assert spies.quantity == 2


def test_two_player_reinforcement_is_delivered_once(db_session, city, monkeypatch):
    _, target = _peer_city(
        db_session,
        city.world_id,
        username="worker_reinforce_target",
        x=32,
        y=32,
    )
    _disable_resolution_side_effects(monkeypatch)

    outgoing = _due_movement(
        db_session,
        origin=city,
        target=target,
        movement_type="reinforce",
        troops={"basic_infantry": 3},
    )
    movement_service.resolve_due_movements(db_session)

    db_session.expire_all()
    target_troops = (
        db_session.query(models.Troop)
        .filter_by(city_id=target.id, unit_type="basic_infantry")
        .one()
    )
    assert target_troops.quantity == 3
    assert (
        db_session.query(models.Movement)
        .filter_by(id=outgoing.id, status="completed")
        .count()
        == 1
    )

    # Completed work is idempotent on another worker pass.
    assert movement_service.resolve_due_movements(db_session) == []
    db_session.refresh(target_troops)
    assert target_troops.quantity == 3


def test_two_player_transport_delivers_once_and_merchants_return(
    db_session,
    city,
    monkeypatch,
):
    _, target = _peer_city(
        db_session,
        city.world_id,
        username="worker_transport_target",
        x=33,
        y=33,
    )
    _disable_resolution_side_effects(monkeypatch)

    outgoing = _due_movement(
        db_session,
        origin=city,
        target=target,
        movement_type="transport",
        resources={"wood": 100},
    )
    movement_service.resolve_due_movements(db_session)

    db_session.expire_all()
    target_after = db_session.query(models.City).filter_by(id=target.id).one()
    assert target_after.wood == pytest.approx(600.0, abs=0.1)

    merchant_return = (
        db_session.query(models.Movement)
        .filter_by(
            origin_city_id=target.id,
            target_city_id=city.id,
            movement_type="transport_return",
            status="ongoing",
        )
        .one()
    )
    merchant_return.arrival_time = FIXED_NOW - timedelta(seconds=1)
    db_session.add(merchant_return)
    db_session.commit()
    movement_service.resolve_due_movements(db_session)

    db_session.expire_all()
    assert (
        db_session.query(models.Movement)
        .filter_by(id=merchant_return.id, status="completed")
        .count()
        == 1
    )
    target_after_second_pass = db_session.query(models.City).filter_by(id=target.id).one()
    assert target_after_second_pass.wood == pytest.approx(600.0, abs=0.1)
