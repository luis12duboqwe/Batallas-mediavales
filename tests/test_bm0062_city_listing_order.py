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


def test_starting_capital_precedes_older_owned_city_id_after_conquest(
    client, db_session, user, city,
):
    # A barbarian may have been seeded before a player's capital and later
    # conquered: lower numeric IDs do not identify the starting capital.
    city.name = "Earlier conquered city"
    city.wood = 0.0
    city.stone = 0.0
    city.iron = 0.0
    city.gold = 0.0
    capital = models.City(
        name="Registered starting capital",
        owner_id=user.id, world_id=city.world_id,
        x=56, y=57,
        wood=45000.0, stone=45000.0, iron=45000.0, gold=45000.0,
    )
    db_session.add(capital)
    db_session.flush()
    assert city.id < capital.id
    db_session.add(models.PlayerWorld(
        user_id=user.id, world_id=city.world_id,
        starting_city_id=capital.id,
    ))
    db_session.commit()

    for _ in range(3):
        response = client.get(
            f"/city/?world_id={city.world_id}", headers=_headers(user),
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert [row["id"] for row in data] == [capital.id, city.id]
        assert data[0]["name"] == "Registered starting capital"
        assert data[0]["wood"] >= 45000


def test_starting_capital_priority_is_scoped_to_requested_world(
    client, db_session, user, city,
):
    first_world = city.world_id
    old_city = city
    later_capital = models.City(
        name="World A capital", owner_id=user.id, world_id=first_world,
        x=64, y=65,
    )
    other_world = models.World(name="World B independent capital")
    db_session.add_all((later_capital, other_world))
    db_session.flush()
    other_capital = models.City(
        name="World B capital", owner_id=user.id, world_id=other_world.id,
        x=34, y=35,
    )
    db_session.add(other_capital)
    db_session.flush()
    db_session.add_all((
        models.PlayerWorld(
            user_id=user.id, world_id=first_world,
            starting_city_id=later_capital.id,
        ),
        models.PlayerWorld(
            user_id=user.id, world_id=other_world.id,
            starting_city_id=other_capital.id,
        ),
    ))
    db_session.commit()

    response_a = client.get(
        f"/city/?world_id={first_world}", headers=_headers(user),
    )
    response_b = client.get(
        f"/city/?world_id={other_world.id}", headers=_headers(user),
    )
    assert response_a.status_code == 200, response_a.text
    assert response_b.status_code == 200, response_b.text
    assert [row["id"] for row in response_a.json()] == [
        later_capital.id, old_city.id,
    ]
    assert [row["id"] for row in response_b.json()] == [other_capital.id]
