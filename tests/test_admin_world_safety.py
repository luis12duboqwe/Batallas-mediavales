from app import models
from app.routers.auth import create_access_token


def _headers(user: models.User) -> dict[str, str]:
    return {
        "Authorization": "Bearer "
        + create_access_token(
            {
                "sub": user.username,
                "type": "access",
                "ver": user.auth_version,
            }
        )
    }


def _create_user(db_session, username: str, *, is_admin: bool = False) -> models.User:
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
        is_admin=is_admin,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_admin_city_creation_requires_owner_world_membership_and_free_coordinates(
    client,
    db_session,
):
    world = db_session.query(models.World).first()
    admin = _create_user(db_session, "worldsafe_admin", is_admin=True)
    owner = _create_user(db_session, "worldsafe_owner")

    payload = {
        "owner_id": owner.id,
        "world_id": world.id,
        "name": "Admin City",
        "x": 33,
        "y": 34,
    }

    not_joined = client.post("/admin/city/create", headers=_headers(admin), json=payload)
    assert not_joined.status_code == 400, not_joined.text
    assert not_joined.json()["detail"] == "Owner has not joined this world"

    db_session.add(models.PlayerWorld(user_id=owner.id, world_id=world.id))
    db_session.commit()

    created = client.post("/admin/city/create", headers=_headers(admin), json=payload)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["world_id"] == world.id
    assert body["x"] == 33
    assert body["y"] == 34

    # owner_id is intentionally not part of the public CityRead contract.
    # Verify the administrative invariant from persistence instead of widening
    # the response schema and leaking extra ownership metadata unnecessarily.
    persisted = db_session.query(models.City).filter_by(id=body["id"]).one()
    assert persisted.owner_id == owner.id
    assert persisted.world_id == world.id

    duplicate = client.post(
        "/admin/city/create",
        headers=_headers(admin),
        json={**payload, "name": "Duplicate"},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"] == "Coordinates already occupied in this world"

    logs = client.get("/admin/logs", headers=_headers(admin), params={"limit": 20})
    assert logs.status_code == 200, logs.text
    create_entries = [entry for entry in logs.json() if entry["action"] == "create_city"]
    assert create_entries
    assert create_entries[0]["user_id"] == admin.id
