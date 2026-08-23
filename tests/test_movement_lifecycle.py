import json
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.routers.auth import create_access_token
from app.services import balance, combat
from app.services import movement as movement_service


FIXED_NOW = datetime(2026, 8, 18, 22, 0, tzinfo=timezone.utc)


def _auth_headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _barbarian_city(db_session, city, *, x=5, y=0):
    barbarian = models.City(
        name="Aldea Bárbara",
        owner_id=None,
        world_id=city.world_id,
        x=x,
        y=y,
        wood=100.0,
        stone=100.0,
        iron=100.0,
        gold=100.0,
        loyalty=100.0,
    )
    db_session.add(barbarian)
    db_session.commit()
    db_session.refresh(barbarian)
    return barbarian


def test_http_can_launch_attack_against_barbarian_without_resolving_world(
    client, db_session, city, user, monkeypatch
):
    user.protection_ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
    troop = models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=10)
    barbarian = _barbarian_city(db_session, city)
    db_session.add(troop)
    db_session.commit()

    monkeypatch.setattr(
        movement_service,
        "_run_dispatch_side_effects",
        lambda *args, **kwargs: None,
    )

    response = client.post(
        "/movement/",
        headers=_auth_headers(user),
        json={
            "origin_city_id": city.id,
            "target_city_id": barbarian.id,
            "movement_type": "attack",
            "troops": {"basic_infantry": 4},
            "resources": {},
            "spy_count": 0,
            "world_id": city.world_id,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ongoing"
    assert payload["troops"] == {"basic_infantry": 4}

    db_session.expire_all()
    troop = (
        db_session.query(models.Troop)
        .filter_by(city_id=city.id, unit_type="basic_infantry")
        .one()
    )
    assert troop.quantity == 6
    assert db_session.query(models.Report).count() == 0

    # A read request must not act as a hidden game worker.
    listed = client.get(
        "/movement/",
        params={"world_id": city.world_id},
        headers=_auth_headers(user),
    )
    assert listed.status_code == 200
    assert db_session.query(models.Report).count() == 0


def test_worker_uses_frozen_movement_army_and_loot_returns_once(
    db_session, city, user, monkeypatch
):
    barbarian = _barbarian_city(db_session, city)
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, 1000.0)
    city.last_production = FIXED_NOW
    db_session.commit()

    monkeypatch.setattr(movement_service, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(combat, "_luck", lambda: 0.0)
    monkeypatch.setattr(
        movement_service,
        "_run_resolution_effect",
        lambda *args, **kwargs: None,
    )

    outgoing = models.Movement(
        origin_city_id=city.id,
        target_city_id=barbarian.id,
        world_id=city.world_id,
        movement_type="attack",
        troops={"basic_infantry": 2},
        resources={},
        spy_count=0,
        arrival_time=FIXED_NOW - timedelta(seconds=1),
        speed_used=1.0,
        status="ongoing",
    )
    db_session.add(outgoing)
    db_session.commit()
    outgoing_id = outgoing.id

    resolved = movement_service.resolve_due_movements(db_session)
    assert [item.id for item in resolved] == [outgoing_id]

    db_session.expire_all()
    completed = db_session.query(models.Movement).filter_by(id=outgoing_id).one()
    assert completed.status == "completed"

    attacker = db_session.query(models.City).filter_by(id=city.id).one()
    defender = db_session.query(models.City).filter_by(id=barbarian.id).one()
    # Loot is not credited at impact time.
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(attacker, resource) == pytest.approx(1000.0)
        assert getattr(defender, resource) < 100.0

    attacker_report = (
        db_session.query(models.Report)
        .filter_by(city_id=city.id, report_type="battle")
        .one()
    )
    report = json.loads(attacker_report.content)
    assert report["attacker"]["initial"] == {"basic_infantry": 2}

    return_move = (
        db_session.query(models.Movement)
        .filter_by(
            target_city_id=city.id,
            movement_type="return",
            status="ongoing",
        )
        .one()
    )
    assert return_move.troops == {"basic_infantry": 2}
    loot = dict(return_move.resources)
    assert sum(loot.values()) > 0

    return_move.arrival_time = FIXED_NOW - timedelta(seconds=1)
    db_session.add(return_move)
    db_session.commit()
    movement_service.resolve_due_movements(db_session)

    db_session.expire_all()
    attacker = db_session.query(models.City).filter_by(id=city.id).one()
    troop = (
        db_session.query(models.Troop)
        .filter_by(city_id=city.id, unit_type="basic_infantry")
        .one()
    )
    assert troop.quantity == 2
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(attacker, resource) == pytest.approx(
            1000.0 + loot.get(resource, 0.0)
        )

    # Re-running the worker cannot apply the completed return a second time.
    assert movement_service.resolve_due_movements(db_session) == []
    db_session.expire_all()
    troop = (
        db_session.query(models.Troop)
        .filter_by(city_id=city.id, unit_type="basic_infantry")
        .one()
    )
    assert troop.quantity == 2
