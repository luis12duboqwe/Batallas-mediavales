"""The funding source defaults to the first city in GET /city/.

The ordering must be deterministic across SQLite and PostgreSQL query plans.
This protects against randomly selecting a newly founded empty city as donor.
"""

from app import models
from app.routers.auth import create_access_token


def _headers(user):
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )
    return {"Authorization": f"Bearer {token}"}


def test_owned_city_list_keeps_earliest_capital_first_with_empty_extra_city(
    client, db_session, user, city,
):
    world_id = city.world_id
    city.name = "Existing capital"
    city.wood = 45000.0
    city.stone = 45000.0
    city.iron = 45000.0
    city.gold = 45000.0
    extra = models.City(
        name="Empty extra city", world_id=world_id, owner_id=user.id,
        x=41, y=42, wood=0.0, stone=0.0, iron=0.0, gold=0.0,
    )
    db_session.add(extra)
    db_session.commit()
    assert city.id < extra.id

    for _ in range(3):
        response = client.get(f"/city/?world_id={world_id}", headers=_headers(user))
        assert response.status_code == 200, response.text
        payload = response.json()
        assert [item["id"] for item in payload] == [city.id, extra.id]
        assert payload[0]["name"] == "Existing capital"
        assert payload[0]["wood"] >= 45000
        assert payload[1]["name"] == "Empty extra city"
        assert payload[1]["wood"] < 100


def test_owned_city_list_does_not_include_another_world(
    client, db_session, user, city,
):
    different_world = models.World(name="City ordering foreign world")
    db_session.add(different_world)
    db_session.flush()
    foreign_city = models.City(
        name="Other world city", owner_id=user.id, world_id=different_world.id,
        x=9, y=10,
    )
    db_session.add(foreign_city)
    db_session.commit()

    response = client.get(
        f"/city/?world_id={city.world_id}", headers=_headers(user)
    )
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [city.id]
