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


def _admin(db_session, username: str, role: str) -> models.User:
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
        is_admin=True,
        admin_role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_capabilities_reason_audit_and_reversal(client, db_session, city):
    support = _admin(db_session, "bm73_support", "support")
    operator = _admin(db_session, "bm73_operator", "operator")
    admin = _admin(db_session, "bm73_admin", "admin")

    denied = client.patch(
        f"/admin/city/{city.id}/resources",
        headers=_headers(support),
        json={"wood": city.wood + 10, "reason": "support should not mutate game"},
    )
    assert denied.status_code == 403, denied.text

    missing_reason = client.patch(
        f"/admin/city/{city.id}/resources",
        headers=_headers(operator),
        json={"wood": city.wood + 10},
    )
    assert missing_reason.status_code == 422, missing_reason.text

    original_wood = city.wood
    corrected_wood = original_wood + 123
    updated = client.patch(
        f"/admin/city/{city.id}/resources",
        headers=_headers(operator),
        json={"wood": corrected_wood, "reason": "Correct support-verified resource drift"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["wood"] == corrected_wood

    logs = client.get("/admin/logs", headers=_headers(admin), params={"limit": 50})
    assert logs.status_code == 200, logs.text
    correction = next(item for item in logs.json() if item["action"] == "update_city_resources")
    assert correction["reason"] == "Correct support-verified resource drift"
    assert correction["before_state"]
    assert correction["after_state"]
    assert correction["reversible"] is True

    reverted = client.post(
        f"/admin/logs/{correction['id']}/revert",
        headers=_headers(admin),
        json={"reason": "Restore pre-correction state"},
    )
    assert reverted.status_code == 200, reverted.text
    db_session.expire_all()
    persisted = db_session.query(models.City).filter_by(id=city.id).one()
    assert persisted.wood == original_wood

    second = client.post(
        f"/admin/logs/{correction['id']}/revert",
        headers=_headers(admin),
        json={"reason": "Must not apply twice"},
    )
    assert second.status_code == 409, second.text


def test_reversal_refuses_to_overwrite_newer_state(client, db_session, city):
    operator = _admin(db_session, "bm73_operator_cas", "operator")
    admin = _admin(db_session, "bm73_admin_cas", "admin")

    first = client.patch(
        f"/admin/city/{city.id}/coordinates",
        headers=_headers(operator),
        json={"x": 71, "y": 72, "reason": "Move city for recovery"},
    )
    assert first.status_code == 200, first.text
    logs = client.get("/admin/logs", headers=_headers(admin), params={"limit": 50}).json()
    first_log = next(item for item in logs if item["action"] == "teleport_city")

    second = client.patch(
        f"/admin/city/{city.id}/coordinates",
        headers=_headers(operator),
        json={"x": 73, "y": 74, "reason": "Later intentional relocation"},
    )
    assert second.status_code == 200, second.text

    stale_revert = client.post(
        f"/admin/logs/{first_log['id']}/revert",
        headers=_headers(admin),
        json={"reason": "Attempt stale rollback"},
    )
    assert stale_revert.status_code == 409, stale_revert.text
    assert stale_revert.json()["detail"] == "Target changed after the audited action"


def test_hard_delete_endpoints_are_not_operational_surface(client, db_session, city, user):
    admin = _admin(db_session, "bm73_admin_delete", "admin")
    delete_user = client.delete(f"/admin/user/{user.id}", headers=_headers(admin))
    delete_city = client.delete(f"/admin/city/{city.id}", headers=_headers(admin))
    assert delete_user.status_code == 404, delete_user.text
    assert delete_city.status_code == 404, delete_city.text
