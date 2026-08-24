from app import models
from app.routers.auth import create_access_token
from app.services import balance, world_gen
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


def _prepare_membership(db_session, user, city, points: int) -> models.PlayerWorld:
    membership = models.PlayerWorld(
        user_id=user.id,
        world_id=city.world_id,
        starting_city_id=city.id,
        expansion_points=points,
    )
    db_session.add(membership)
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, 5000.0)
    city.last_production = utc_now()
    db_session.add(city)
    db_session.commit()
    return membership


def test_direct_city_creation_endpoint_is_closed(client, user, city):
    response = client.post(
        "/city/",
        headers=_headers(user),
        json={
            "name": "Free City",
            "world_id": city.world_id,
            "x": 4,
            "y": 4,
        },
    )

    assert response.status_code == 409
    assert "/expansion/found" in response.json()["detail"]


def test_expansion_status_and_camp_founding_api(
    client,
    db_session,
    user,
    city,
    monkeypatch,
):
    membership = _prepare_membership(
        db_session,
        user,
        city,
        balance.SETTLEMENT_EXPANSION_POINT_COSTS["camp"],
    )
    monkeypatch.setattr(world_gen, "get_tile_type", lambda x, y: "grass")

    before = client.get(
        "/expansion/status",
        params={"world_id": city.world_id},
        headers=_headers(user),
    )
    assert before.status_code == 200, before.text
    assert before.json()["expansion_points"] == balance.SETTLEMENT_EXPANSION_POINT_COSTS["camp"]
    assert before.json()["city_count"] == 1
    assert before.json()["camp_count"] == 0

    founded = client.post(
        "/expansion/found",
        headers=_headers(user),
        json={
            "origin_city_id": city.id,
            "name": "Camp API",
            "x": 12,
            "y": 13,
            "settlement_type": "camp",
        },
    )
    assert founded.status_code == 200, founded.text
    payload = founded.json()
    assert payload["settlement_type"] == "camp"
    assert payload["population_max"] == balance.CAMP_POPULATION_MAX

    map_response = client.get(
        "/map/tiles",
        params={"world_id": city.world_id, "x": 12, "y": 13, "radius": 0},
        headers=_headers(user),
    )
    assert map_response.status_code == 200, map_response.text
    tile = map_response.json()["tiles"][0]
    assert tile["city_id"] == payload["id"]
    assert tile["settlement_type"] == "camp"
    assert tile["owner_id"] == user.id

    db_session.refresh(membership)
    assert membership.expansion_points == 0

    after = client.get(
        "/expansion/status",
        params={"world_id": city.world_id},
        headers=_headers(user),
    )
    assert after.status_code == 200
    assert after.json()["city_count"] == 1
    assert after.json()["camp_count"] == 1


def test_expansion_api_rejects_unknown_settlement_type(client, db_session, user, city):
    _prepare_membership(db_session, user, city, 10)

    response = client.post(
        "/expansion/found",
        headers=_headers(user),
        json={
            "origin_city_id": city.id,
            "name": "Invalid",
            "x": 14,
            "y": 14,
            "settlement_type": "outpost",
        },
    )
    assert response.status_code == 422


def test_camp_promotion_api(client, db_session, user, city):
    membership = _prepare_membership(
        db_session,
        user,
        city,
        balance.CAMP_PROMOTION_POINT_COST,
    )
    camp = models.City(
        name="Promotion API",
        owner_id=user.id,
        world_id=city.world_id,
        x=15,
        y=15,
        settlement_type="camp",
        population_max=balance.CAMP_POPULATION_MAX,
        last_production=utc_now(),
    )
    for resource in balance.RESOURCE_FIELDS:
        setattr(camp, resource, 5000.0)
    db_session.add(camp)
    db_session.flush()
    for definition in balance.CAMP_STARTER_BUILDINGS:
        db_session.add(
            models.Building(
                city_id=camp.id,
                name=definition["name"],
                level=definition["level"],
            )
        )
    db_session.commit()

    response = client.post(
        f"/expansion/camps/{camp.id}/promote",
        headers=_headers(user),
    )
    assert response.status_code == 200, response.text
    assert response.json()["settlement_type"] == "city"

    db_session.refresh(membership)
    assert membership.expansion_points == 0


def test_map_tiles_are_clamped_to_world_boundaries(client, db_session, user, city):
    _prepare_membership(db_session, user, city, 0)
    world = db_session.query(models.World).filter(models.World.id == city.world_id).one()
    map_size = int(world.map_size)

    for x, y in ((0, 0), (map_size - 1, map_size - 1)):
        response = client.get(
            "/map/tiles",
            params={"world_id": city.world_id, "x": x, "y": y, "radius": 8},
            headers=_headers(user),
        )
        assert response.status_code == 200, response.text
        tiles = response.json()["tiles"]
        assert tiles
        assert all(0 <= tile["x"] < map_size for tile in tiles)
        assert all(0 <= tile["y"] < map_size for tile in tiles)


def test_legacy_conquest_found_route_is_not_exposed(
    client,
    db_session,
    user,
    city,
):
    _prepare_membership(db_session, user, city, 0)

    response = client.post(
        "/conquest/found",
        headers=_headers(user),
        json={
            "origin_city_id": city.id,
            "name": "Legacy Bypass",
            "x": 16,
            "y": 16,
        },
    )

    assert response.status_code == 404
    assert (
        db_session.query(models.City)
        .filter_by(owner_id=user.id, world_id=city.world_id)
        .count()
        == 1
    )
