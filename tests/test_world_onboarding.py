from app import models
from app.routers.auth import create_access_token


def _auth_headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_join_world_creates_exactly_one_starting_city(client, db_session, user):
    world = db_session.query(models.World).first()
    headers = _auth_headers(user)

    first = client.post(f"/worlds/{world.id}/join", headers=headers)
    assert first.status_code == 200
    first_membership = first.json()
    assert first_membership["world_id"] == world.id
    assert first_membership["starting_city_id"] is not None

    starting_city = (
        db_session.query(models.City)
        .filter(models.City.id == first_membership["starting_city_id"])
        .one()
    )
    assert starting_city.owner_id == user.id
    assert starting_city.world_id == world.id
    assert 0 <= starting_city.x < world.map_size
    assert 0 <= starting_city.y < world.map_size
    assert starting_city.tile_type != "water"
    assert (
        db_session.query(models.Oasis)
        .filter(
            models.Oasis.world_id == world.id,
            models.Oasis.x == starting_city.x,
            models.Oasis.y == starting_city.y,
        )
        .count()
        == 0
    )

    second = client.post(f"/worlds/{world.id}/join", headers=headers)
    assert second.status_code == 200
    second_membership = second.json()
    assert second_membership["id"] == first_membership["id"]
    assert second_membership["starting_city_id"] == first_membership["starting_city_id"]

    assert (
        db_session.query(models.PlayerWorld)
        .filter(
            models.PlayerWorld.user_id == user.id,
            models.PlayerWorld.world_id == world.id,
        )
        .count()
        == 1
    )
    assert (
        db_session.query(models.City)
        .filter(
            models.City.owner_id == user.id,
            models.City.world_id == world.id,
        )
        .count()
        == 1
    )

    db_session.refresh(user)
    assert user.world_id == world.id


def test_selecting_unjoined_world_runs_same_onboarding(client, db_session, user):
    world = models.World(
        name="SecondWorld",
        speed_modifier=1.0,
        resource_modifier=1.0,
        map_size=25,
        is_active=True,
    )
    db_session.add(world)
    db_session.commit()
    db_session.refresh(world)

    response = client.post(
        "/worlds/active",
        json={"world_id": world.id},
        headers=_auth_headers(user),
    )
    assert response.status_code == 200
    membership = response.json()
    assert membership["starting_city_id"] is not None

    city = (
        db_session.query(models.City)
        .filter(models.City.id == membership["starting_city_id"])
        .one()
    )
    assert city.owner_id == user.id
    assert city.world_id == world.id


def test_legacy_membership_reuses_existing_city(client, db_session, user):
    world = db_session.query(models.World).first()
    legacy_city = models.City(
        name="Ciudad heredada",
        owner_id=user.id,
        world_id=world.id,
        x=4,
        y=7,
        tile_type="grass",
    )
    membership = models.PlayerWorld(user_id=user.id, world_id=world.id)
    db_session.add_all([legacy_city, membership])
    db_session.commit()
    db_session.refresh(legacy_city)
    db_session.refresh(membership)
    assert membership.starting_city_id is None

    response = client.post(
        f"/worlds/{world.id}/join",
        headers=_auth_headers(user),
    )
    assert response.status_code == 200
    assert response.json()["starting_city_id"] == legacy_city.id
    assert (
        db_session.query(models.City)
        .filter(
            models.City.owner_id == user.id,
            models.City.world_id == world.id,
        )
        .count()
        == 1
    )


def test_inactive_world_does_not_create_membership_or_city(client, db_session, user):
    world = models.World(
        name="ClosedWorld",
        speed_modifier=1.0,
        resource_modifier=1.0,
        map_size=25,
        is_active=False,
    )
    db_session.add(world)
    db_session.commit()
    db_session.refresh(world)

    response = client.post(
        f"/worlds/{world.id}/join",
        headers=_auth_headers(user),
    )
    assert response.status_code == 404
    assert (
        db_session.query(models.PlayerWorld)
        .filter(
            models.PlayerWorld.user_id == user.id,
            models.PlayerWorld.world_id == world.id,
        )
        .count()
        == 0
    )
    assert (
        db_session.query(models.City)
        .filter(
            models.City.owner_id == user.id,
            models.City.world_id == world.id,
        )
        .count()
        == 0
    )
