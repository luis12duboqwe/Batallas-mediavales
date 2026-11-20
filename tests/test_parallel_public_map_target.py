"""Minimal public targeting metadata must not expose other players' private cities."""

from app import models
from app.routers.auth import create_access_token
from app.services import world_membership


def _headers(user):
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )
    return {"Authorization": f"Bearer {token}"}


def _rival_city(db_session, world_id):
    rival = models.User(
        username="target_rival",
        email="target_rival@example.com",
        hashed_password="test",
        is_verified=True,
    )
    db_session.add(rival)
    db_session.flush()
    target = models.City(
        name="Public Target", owner_id=rival.id, world_id=world_id, x=21, y=22
    )
    db_session.add(target)
    db_session.commit()
    return target, rival


def test_public_target_exposes_only_map_metadata_not_private_status(
    client, db_session, user, city
):
    world_membership.join_world(db_session, user, city.world_id)
    target, rival = _rival_city(db_session, city.world_id)
    headers = _headers(user)

    response = client.get(
        f"/map/city/{target.id}",
        params={"world_id": city.world_id}, headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": target.id,
        "name": "Public Target",
        "x": 21,
        "y": 22,
        "world_id": city.world_id,
        "settlement_type": "city",
        "owner_id": rival.id,
        "owner_name": rival.username,
    }

    private = client.get(
        f"/city/{target.id}/status",
        params={"world_id": city.world_id}, headers=headers,
    )
    assert private.status_code == 404
    assert "wood" not in response.json()
    assert "troops" not in response.json()


def test_public_target_shows_own_city_and_barbarian_without_mutations(
    client, db_session, user, city
):
    world_membership.join_world(db_session, user, city.world_id)
    barbarian = models.City(
        name="Barbarian Target", owner_id=None, world_id=city.world_id, x=23, y=24
    )
    db_session.add(barbarian)
    db_session.commit()
    headers = _headers(user)
    own = client.get(f"/map/city/{city.id}", params={"world_id": city.world_id}, headers=headers)
    barb = client.get(f"/map/city/{barbarian.id}", params={"world_id": city.world_id}, headers=headers)
    assert own.status_code == 200
    assert own.json()["name"] == city.name
    assert own.json()["owner_id"] == user.id
    assert barb.status_code == 200
    assert barb.json()["name"] == "Barbarian Target"
    assert barb.json()["owner_id"] is None
    assert barb.json()["owner_name"] is None


def test_public_target_requires_joined_world_and_hides_foreign_world(
    client, db_session, user, city
):
    world_membership.join_world(db_session, user, city.world_id)
    foreign_world = models.World(
        name="Unjoined target world", map_size=64, speed_modifier=1.0, resource_modifier=1.0
    )
    db_session.add(foreign_world)
    db_session.flush()
    foreign = models.City(
        name="Secret Foreign World", owner_id=None,
        world_id=foreign_world.id, x=12, y=13
    )
    db_session.add(foreign)
    db_session.commit()
    headers = _headers(user)
    denied = client.get(
        f"/map/city/{foreign.id}",
        params={"world_id": foreign_world.id}, headers=headers,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["error_code"] == "world_access_denied"
    hidden = client.get(
        f"/map/city/{foreign.id}",
        params={"world_id": city.world_id}, headers=headers,
    )
    assert hidden.status_code == 404
    assert "Secret Foreign World" not in hidden.text
    absent = client.get(
        "/map/city/99999999",
        params={"world_id": city.world_id}, headers=headers,
    )
    assert absent.status_code == 404
    guest = client.get(
        f"/map/city/{city.id}", params={"world_id": city.world_id}
    )
    assert guest.status_code in (401, 403)
