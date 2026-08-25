from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.routers.auth import create_access_token
from app.services import balance
from app.services import movement as movement_service
from app.utils import utc_now


def _headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _other_player_city(
    db_session,
    world_id: int,
    *,
    username: str,
    x: int,
    y: int,
    protected: bool = False,
):
    protection_end = datetime.now(timezone.utc) + timedelta(hours=24)
    if not protected:
        protection_end = datetime.now(timezone.utc) - timedelta(hours=1)
    other = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
        protection_ends_at=protection_end,
    )
    db_session.add(other)
    db_session.flush()
    target = models.City(
        name=f"Capital {username}",
        owner_id=other.id,
        world_id=world_id,
        x=x,
        y=y,
        wood=500,
        stone=500,
        iron=500,
        gold=500,
        last_production=utc_now(),
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(other)
    db_session.refresh(target)
    return other, target


def _disable_dispatch_noise(monkeypatch):
    monkeypatch.setattr(
        movement_service.anticheat,
        "check_action_speed",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        movement_service.anticheat,
        "check_movement_legitimacy",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        movement_service,
        "_run_dispatch_side_effects",
        lambda *args, **kwargs: None,
    )


@pytest.mark.parametrize(
    ("movement_type", "troop_type", "payload_extra"),
    [
        ("attack", "basic_infantry", {"troops": {"basic_infantry": 2}}),
        ("spy", "spy", {"spy_count": 2}),
        ("reinforce", "basic_infantry", {"troops": {"basic_infantry": 2}}),
    ],
)
def test_same_world_two_player_movement_can_be_dispatched_and_reserved_once(
    client,
    db_session,
    user,
    city,
    monkeypatch,
    movement_type,
    troop_type,
    payload_extra,
):
    user.protection_ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, 1000)
    city.last_production = utc_now()
    db_session.add_all([user, city])
    _, target = _other_player_city(
        db_session,
        city.world_id,
        username=f"peer_{movement_type}",
        x=20,
        y=21,
    )

    db_session.add(models.Troop(city_id=city.id, unit_type=troop_type, quantity=5))
    db_session.commit()
    _disable_dispatch_noise(monkeypatch)

    payload = {
        "origin_city_id": city.id,
        "target_city_id": target.id,
        "movement_type": movement_type,
        "troops": {},
        "resources": {},
        "spy_count": 0,
        "world_id": city.world_id,
        **payload_extra,
    }
    response = client.post("/movement/", json=payload, headers=_headers(user))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["movement_type"] == movement_type
    assert body["world_id"] == city.world_id
    assert body["origin_city_id"] == city.id
    assert body["target_city_id"] == target.id
    assert body["status"] == "ongoing"

    db_session.expire_all()
    persisted = db_session.query(models.Movement).filter_by(id=body["id"]).one()
    assert persisted.world_id == city.world_id

    remaining = (
        db_session.query(models.Troop)
        .filter_by(city_id=city.id, unit_type=troop_type)
        .one()
    )
    assert remaining.quantity == 3


def test_generic_movement_endpoint_cannot_bypass_market_transport_rules(
    client,
    db_session,
    user,
    city,
):
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, 1000)
    city.last_production = utc_now()
    db_session.add(city)
    _, target = _other_player_city(
        db_session,
        city.world_id,
        username="peer_transport_bypass",
        x=22,
        y=23,
    )
    db_session.commit()

    response = client.post(
        "/movement/",
        headers=_headers(user),
        json={
            "origin_city_id": city.id,
            "target_city_id": target.id,
            "movement_type": "transport",
            "troops": {},
            "resources": {"wood": 125},
            "spy_count": 0,
            "world_id": city.world_id,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "movement_creation_failed"
    assert "market service" in response.json()["detail"]["message"]
    db_session.expire_all()
    origin_after = db_session.query(models.City).filter_by(id=city.id).one()
    assert origin_after.wood == pytest.approx(1000, abs=0.1)
    assert db_session.query(models.Movement).count() == 0


@pytest.mark.parametrize("movement_type", ["attack", "spy", "reinforce", "transport"])
def test_cross_world_player_movement_is_rejected(
    client,
    db_session,
    user,
    city,
    movement_type,
):
    user.protection_ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add(user)
    other_world = models.World(name=f"Foreign {movement_type}", is_active=True)
    db_session.add(other_world)
    db_session.commit()
    db_session.refresh(other_world)
    _, target = _other_player_city(
        db_session,
        other_world.id,
        username=f"foreign_{movement_type}",
        x=24,
        y=25,
    )

    payload = {
        "origin_city_id": city.id,
        "target_city_id": target.id,
        "movement_type": movement_type,
        "troops": {"basic_infantry": 1} if movement_type in {"attack", "reinforce"} else {},
        "resources": {"wood": 1} if movement_type == "transport" else {},
        "spy_count": 1 if movement_type == "spy" else 0,
        "world_id": city.world_id,
    }
    response = client.post("/movement/", json=payload, headers=_headers(user))

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "target_not_found"
    assert db_session.query(models.Movement).count() == 0


@pytest.mark.parametrize(
    ("movement_type", "payload_extra"),
    [
        ("attack", {"troops": {"basic_infantry": 1}}),
        ("spy", {"spy_count": 1}),
    ],
)
def test_player_cannot_launch_hostility_against_another_owned_city(
    client,
    db_session,
    user,
    city,
    second_city,
    movement_type,
    payload_extra,
):
    user.protection_ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add(user)
    troop_type = "basic_infantry" if movement_type == "attack" else "spy"
    db_session.add(models.Troop(city_id=city.id, unit_type=troop_type, quantity=2))
    db_session.commit()

    response = client.post(
        "/movement/",
        headers=_headers(user),
        json={
            "origin_city_id": city.id,
            "target_city_id": second_city.id,
            "movement_type": movement_type,
            "troops": {},
            "resources": {},
            "spy_count": 0,
            "world_id": city.world_id,
            **payload_extra,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "invalid_hostile_target"
    assert db_session.query(models.Movement).count() == 0
