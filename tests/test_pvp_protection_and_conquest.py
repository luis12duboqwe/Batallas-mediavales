from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.routers.auth import create_access_token
from app.services import combat
from app.services import conquest as conquest_service


def _auth_headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _player_city(db_session, world_id: int, *, username: str, x: int, y: int):
    player = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
        protection_ends_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(player)
    db_session.flush()
    city = models.City(
        name=f"Capital {username}",
        owner_id=player.id,
        world_id=world_id,
        x=x,
        y=y,
        loyalty=25.0,
    )
    db_session.add(city)
    db_session.commit()
    db_session.refresh(player)
    db_session.refresh(city)
    return player, city


def _barbarian_city(db_session, world_id: int, *, x: int, y: int, loyalty: float = 25.0):
    city = models.City(
        name="Aldea Bárbara",
        owner_id=None,
        world_id=world_id,
        x=x,
        y=y,
        loyalty=loyalty,
    )
    db_session.add(city)
    db_session.commit()
    db_session.refresh(city)
    return city


def test_player_city_conquest_is_rejected_before_gameplay_mutation(db_session, city):
    _, target = _player_city(
        db_session,
        city.world_id,
        username="defender_conquest",
        x=7,
        y=7,
    )
    noble = models.Troop(city_id=city.id, unit_type="noble", quantity=4)
    db_session.add(noble)
    db_session.commit()

    original_owner_id = target.owner_id
    original_loyalty = target.loyalty
    original_nobles = noble.quantity

    with pytest.raises(ValueError, match="Player cities cannot be conquered"):
        conquest_service.resolve_conquest(
            db_session,
            city,
            target,
            {"noble": 1},
        )

    db_session.expire_all()
    target_after = db_session.query(models.City).filter_by(id=target.id).one()
    noble_after = (
        db_session.query(models.Troop)
        .filter_by(city_id=city.id, unit_type="noble")
        .one()
    )
    assert target_after.owner_id == original_owner_id
    assert target_after.loyalty == original_loyalty
    assert noble_after.quantity == original_nobles


def test_cross_world_barbarian_conquest_is_rejected(db_session, city):
    other_world = models.World(name="Other conquest world", is_active=True)
    db_session.add(other_world)
    db_session.commit()
    db_session.refresh(other_world)
    target = _barbarian_city(db_session, other_world.id, x=2, y=2)
    db_session.add(models.Troop(city_id=city.id, unit_type="noble", quantity=1))
    db_session.commit()

    with pytest.raises(ValueError, match="Cross-world conquest is not allowed"):
        conquest_service.resolve_conquest(db_session, city, target, {"noble": 1})


def test_barbarian_city_can_still_be_conquered(db_session, city, monkeypatch):
    target = _barbarian_city(db_session, city.world_id, x=9, y=9, loyalty=25.0)
    db_session.add(models.Troop(city_id=city.id, unit_type="noble", quantity=1))
    db_session.commit()

    # Keep the canonical combat engine, but make its luck and loyalty roll deterministic.
    monkeypatch.setattr(combat, "_luck", lambda: 0.0)
    monkeypatch.setattr(combat.random, "randint", lambda low, high: 25)

    victory, conquered = conquest_service.resolve_conquest(
        db_session,
        city,
        target,
        {"noble": 1},
    )

    db_session.refresh(target)
    assert victory is True
    assert conquered is True
    assert target.owner_id == city.owner_id
    assert target.loyalty == 25.0


@pytest.mark.parametrize(
    ("movement_type", "payload_extra"),
    [
        ("attack", {"troops": {"basic_infantry": 1}}),
        ("spy", {"spy_count": 1}),
    ],
)
def test_protected_attacker_cannot_launch_pvp_hostility(
    client,
    db_session,
    user,
    city,
    movement_type,
    payload_extra,
):
    _, target = _player_city(
        db_session,
        city.world_id,
        username=f"target_{movement_type}",
        x=11 if movement_type == "attack" else 12,
        y=11,
    )
    db_session.add(
        models.Troop(
            city_id=city.id,
            unit_type="basic_infantry" if movement_type == "attack" else "spy",
            quantity=2,
        )
    )
    db_session.commit()

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
    response = client.post("/movement/", json=payload, headers=_auth_headers(user))

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "protection_active"
    assert db_session.query(models.Movement).count() == 0


def test_protected_defender_blocks_pvp_spy(client, db_session, user, city):
    user.protection_ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add(user)
    defender, target = _player_city(
        db_session,
        city.world_id,
        username="protected_defender",
        x=14,
        y=14,
    )
    defender.protection_ends_at = datetime.now(timezone.utc) + timedelta(hours=24)
    db_session.add(defender)
    db_session.add(models.Troop(city_id=city.id, unit_type="spy", quantity=2))
    db_session.commit()

    response = client.post(
        "/movement/",
        headers=_auth_headers(user),
        json={
            "origin_city_id": city.id,
            "target_city_id": target.id,
            "movement_type": "spy",
            "troops": {},
            "resources": {},
            "spy_count": 1,
            "world_id": city.world_id,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "target_protected"
    assert db_session.query(models.Movement).count() == 0


def test_protected_player_can_attack_barbarian_for_pve_progress(
    client,
    db_session,
    user,
    city,
    monkeypatch,
):
    target = _barbarian_city(db_session, city.world_id, x=15, y=15)
    db_session.add(models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=2))
    db_session.commit()

    from app.services import movement as movement_service

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
            "target_city_id": target.id,
            "movement_type": "attack",
            "troops": {"basic_infantry": 1},
            "resources": {},
            "spy_count": 0,
            "world_id": city.world_id,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["movement_type"] == "attack"
