from uuid import uuid4

from app import models
from app.routers.auth import create_access_token
from app.services import balance


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.username, 'type': 'access', 'ver': user.auth_version})}"}


def test_admin_created_world_version_is_pinned(client, db_session, user):
    user.is_admin = True
    db_session.commit()
    response = client.post(
        "/worlds/create", headers={**_headers(user), "X-Admin-Reason": "BM0062 creation"},
        json={"name": "New alliance wonder season", "lifecycle_status": "draft"},
    )
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["wonder_rules_version"] == "alliance-v2"
    world = db_session.get(models.World, created["id"])
    assert world.wonder_rules_version == "alliance-v2"
    assert db_session.query(models.World).filter_by(name="TestWorld").one().wonder_rules_version == "legacy-v1"


def test_authenticated_wonder_routes_and_validation(client, db_session, user, city):
    city.world.wonder_rules_version = "alliance-v2"
    ally = models.Alliance(name="Test alliance", leader_id=user.id, world_id=city.world_id)
    db_session.add(ally)
    db_session.flush()
    db_session.add(models.AllianceMember(alliance_id=ally.id, user_id=user.id, rank=3))
    db_session.add_all([
        models.Building(city_id=city.id, name="town_hall", level=20),
        models.Building(city_id=city.id, name="warehouse", level=20),
        models.Building(city_id=city.id, name="cathedral", level=10),
    ])
    for field in balance.RESOURCE_FIELDS:
        setattr(city, field, 45000.0)
    db_session.commit()
    headers = _headers(user)
    path = f"/building/wonder/funding?city_id={city.id}&world_id={city.world_id}"
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["remaining"]["wood"] == 10000
    assert response.json()["rules_version"] == "alliance-v2"

    request = {
        "source_city_id": city.id, "target_city_id": city.id,
        "idempotency_key": str(uuid4()).replace("-", ""),
        "wood": 500, "stone": 0, "iron": 0, "gold": 0,
    }
    endpoint = f"/building/wonder/contribute?world_id={city.world_id}"
    submitted = client.post(endpoint, json=request, headers=headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["funded"]["wood"] == 500
    idem = client.post(endpoint, json=request, headers=headers)
    assert idem.status_code == 200
    assert idem.json()["funded"]["wood"] == 500
    bad = client.post(endpoint, json={**request, "wood": 700}, headers=headers)
    assert bad.status_code == 400
    assert "Idempotency" in bad.json()["detail"]["message"]
    invalid_float = client.post(endpoint, json={**request, "idempotency_key": "other-unique-123", "wood": 0.5}, headers=headers)
    assert invalid_float.status_code == 422
    invalid_bool = client.post(endpoint, json={**request, "idempotency_key": "other-unique-456", "wood": True}, headers=headers)
    assert invalid_bool.status_code == 422
    unauth = client.get(path)
    assert unauth.status_code in {401, 403}


def test_other_world_and_nonmember_must_not_read_wonder(client, db_session, user, city):
    city.world.wonder_rules_version = "alliance-v2"
    db_session.commit()
    without_alliance = client.get(
        f"/building/wonder/funding?city_id={city.id}&world_id={city.world_id}",
        headers=_headers(user),
    )
    assert without_alliance.status_code == 403
    crossworld = client.post(
        "/building/wonder/contribute?world_id=999999",
        headers=_headers(user),
        json={
            "source_city_id": city.id,
            "target_city_id": city.id,
            "idempotency_key": "some-key-123",
            "wood": 1,
        },
    )
    assert crossworld.status_code == 400
    assert db_session.query(models.WonderContribution).count() == 0
