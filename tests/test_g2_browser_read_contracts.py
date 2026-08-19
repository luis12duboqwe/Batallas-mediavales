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


def test_g2_browser_read_contracts_are_200(client, db_session, user):
    """Reproduce the exact three GET requests made by accepted G2 views."""

    world = db_session.query(models.World).first()
    membership = world_membership.join_world(db_session, user, world.id)
    city = db_session.query(models.City).filter_by(id=membership.starting_city_id).one()
    headers = _headers(user)

    requests = [
        ("/troop/available", {"city_id": city.id, "world_id": world.id}),
        ("/map/tiles", {"world_id": world.id, "x": city.x, "y": city.y, "radius": 10}),
        ("/movement/", {"world_id": world.id}),
    ]

    for path, params in requests:
        response = client.get(path, params=params, headers=headers)
        assert response.status_code == 200, (
            f"{path} returned {response.status_code}: {response.text}"
        )
