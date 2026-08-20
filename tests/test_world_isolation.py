from app import models
from app.routers.auth import create_access_token
from app.services import world_membership


def _headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _create_foreign_world(db_session) -> models.World:
    world = models.World(
        name="ForeignWorld",
        speed_modifier=1.0,
        resource_modifier=1.0,
        map_size=100,
        is_active=True,
    )
    db_session.add(world)
    db_session.commit()
    db_session.refresh(world)
    return world


def test_world_scoped_reads_require_durable_membership(client, db_session, user):
    joined_world = db_session.query(models.World).first()
    world_membership.join_world(db_session, user, joined_world.id)
    foreign_world = _create_foreign_world(db_session)
    headers = _headers(user)

    foreign_oasis = models.Oasis(
        world_id=foreign_world.id,
        x=11,
        y=12,
        resource_type="wood",
        bonus_percent=25,
    )
    db_session.add(foreign_oasis)
    db_session.commit()
    db_session.refresh(foreign_oasis)

    requests = [
        ("/map/tiles", {"world_id": foreign_world.id, "x": 0, "y": 0, "radius": 2}),
        ("/ranking/players", {"world_id": foreign_world.id}),
        ("/ranking/alliances", {"world_id": foreign_world.id}),
        ("/ranking/search", {"world_id": foreign_world.id, "query": "test"}),
        ("/market/offers", {"world_id": foreign_world.id}),
    ]

    for path, params in requests:
        response = client.get(path, params=params, headers=headers)
        assert response.status_code == 403, (
            f"{path} leaked unjoined world {foreign_world.id}: "
            f"{response.status_code} {response.text}"
        )
        assert response.json()["detail"]["code"] == "world_access_denied"

    oasis_response = client.get(f"/map/oasis/{foreign_oasis.id}", headers=headers)
    assert oasis_response.status_code == 403
    assert oasis_response.json()["detail"]["code"] == "world_access_denied"


def test_joined_world_reads_remain_available(client, db_session, user):
    world = db_session.query(models.World).first()
    membership = world_membership.join_world(db_session, user, world.id)
    city = db_session.query(models.City).filter_by(id=membership.starting_city_id).one()
    headers = _headers(user)

    requests = [
        ("/map/tiles", {"world_id": world.id, "x": city.x, "y": city.y, "radius": 2}),
        ("/ranking/players", {"world_id": world.id}),
        ("/ranking/alliances", {"world_id": world.id}),
        ("/ranking/search", {"world_id": world.id, "query": user.username}),
        ("/market/offers", {"world_id": world.id}),
    ]

    for path, params in requests:
        response = client.get(path, params=params, headers=headers)
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text}"
