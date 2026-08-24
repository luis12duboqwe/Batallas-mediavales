from datetime import timedelta

from app import models
from app.routers.auth import create_access_token
from app.services import balance
from app.utils import utc_now


def _auth_headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_city_list_exposes_farm_capacity_without_persisting_bonus(
    client, db_session, user, city, second_city
):
    city.population_max = 100
    second_city.population_max = 120
    db_session.add_all(
        [
            models.Building(city_id=city.id, name="farm", level=2),
            models.Building(city_id=second_city.id, name="farm", level=1),
        ]
    )
    db_session.commit()

    response = client.get(
        "/city/",
        params={"world_id": city.world_id},
        headers=_auth_headers(user),
    )
    assert response.status_code == 200, response.text
    payload = {entry["id"]: entry for entry in response.json()}

    assert payload[city.id]["population_max"] == 100
    assert payload[city.id]["population_capacity"] == (
        100 + 2 * balance.POPULATION_PER_FARM_LEVEL
    )
    assert payload[second_city.id]["population_max"] == 120
    assert payload[second_city.id]["population_capacity"] == (
        120 + balance.POPULATION_PER_FARM_LEVEL
    )

    # Force another query/commit boundary after serialization. The effective
    # capacity must never be autoflushed into the mapped population_max column.
    db_session.commit()
    db_session.expire_all()
    persisted_city = db_session.query(models.City).filter_by(id=city.id).one()
    persisted_second = db_session.query(models.City).filter_by(id=second_city.id).one()
    assert persisted_city.population_max == 100
    assert persisted_second.population_max == 120


def test_city_status_includes_authoritative_research_queue(
    client, db_session, user, city
):
    queue = models.ResearchQueue(
        city_id=city.id,
        tech_name="heavy_infantry",
        finish_time=utc_now() + timedelta(minutes=5),
        paid_cost={"wood": 500.0, "stone": 400.0, "iron": 300.0, "gold": 50.0},
    )
    db_session.add(queue)
    db_session.commit()

    response = client.get(
        f"/city/{city.id}/status",
        params={"world_id": city.world_id},
        headers=_auth_headers(user),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["population_used"] == payload["population"]
    assert payload["population_capacity"] == payload["population_max"]
    assert payload["population_available"] >= 0
    assert len(payload["research_queue"]) == 1
    assert payload["research_queue"][0]["id"] == queue.id
    assert payload["research_queue"][0]["tech_name"] == "heavy_infantry"
