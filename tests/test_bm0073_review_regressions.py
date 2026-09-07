from datetime import timedelta

import pytest

from app import models
from app.routers import event as event_router
from app.routers import premium as premium_router
from app.routers import season as season_router
from app.routers.auth import create_access_token
from app.services import admin_permissions
from app.services import premium as premium_service
from app.utils import utc_now


def _headers(user: models.User, *, reason: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": "Bearer "
        + create_access_token(
            {
                "sub": user.username,
                "type": "access",
                "ver": user.auth_version,
            }
        )
    }
    if reason is not None:
        headers["X-Admin-Reason"] = reason
    return headers


def _user(
    db_session,
    username: str,
    *,
    role: str | None = None,
    is_admin: bool | None = None,
) -> models.User:
    enabled = (role is not None) if is_admin is None else is_admin
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
        is_admin=enabled,
        admin_role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_unknown_admin_role_fails_closed(db_session):
    user = _user(
        db_session,
        "bm73_unknown_role",
        role="future_superuser",
        is_admin=True,
    )
    assert admin_permissions.effective_admin_role(user) is None
    assert admin_permissions.has_capability(user, "admin.roles") is False
    assert admin_permissions.has_capability(user, "world.manage") is False


def test_full_admin_cannot_demote_itself(client, db_session):
    admin = _user(db_session, "bm73_self_demote", role="admin")
    response = client.patch(
        f"/admin/user/{admin.id}/role",
        headers=_headers(admin),
        json={
            "enabled": True,
            "role": "support",
            "reason": "This must not remove the last role manager",
        },
    )
    assert response.status_code == 400, response.text
    db_session.expire_all()
    persisted = db_session.query(models.User).filter_by(id=admin.id).one()
    assert persisted.is_admin is True
    assert persisted.admin_role == "admin"


def test_support_reopen_clears_resolution_timestamp_and_explicit_null_unassigns(
    client, db_session
):
    requester = _user(db_session, "bm73_reopen_requester")
    support = _user(db_session, "bm73_reopen_support", role="support")

    created = client.post(
        "/support/cases",
        headers=_headers(requester),
        json={"subject": "Reopen me", "description": "Regression coverage"},
    )
    assert created.status_code == 200, created.text
    case_id = created.json()["id"]

    resolved = client.patch(
        f"/support/admin/cases/{case_id}",
        headers=_headers(support),
        json={
            "status": "resolved",
            "resolution": "Initial resolution",
            "assigned_to_id": support.id,
            "reason": "Resolve after investigation",
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolved_at"] is not None
    assert resolved.json()["assigned_to_id"] == support.id

    reopened = client.patch(
        f"/support/admin/cases/{case_id}",
        headers=_headers(support),
        json={
            "status": "in_progress",
            "assigned_to_id": None,
            "reason": "New evidence requires another investigation",
        },
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "in_progress"
    assert reopened.json()["resolved_at"] is None
    assert reopened.json()["assigned_to_id"] is None


def test_event_creation_rolls_back_when_audit_write_fails(
    client, db_session, monkeypatch
):
    admin = _user(db_session, "bm73_event_atomic", role="admin")
    world = db_session.query(models.World).first()
    before = db_session.query(models.WorldEvent).count()

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(event_router.admin_service, "log_action", fail_audit)
    now = utc_now()
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.post(
            "/event/create",
            headers=_headers(admin, reason="Atomic event regression"),
            json={
                "world_id": world.id,
                "event_type": "DOUBLE_RESOURCES",
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
            },
        )

    db_session.rollback()
    assert db_session.query(models.WorldEvent).count() == before


def test_premium_grant_rolls_back_when_audit_write_fails(
    client, db_session, monkeypatch
):
    admin = _user(db_session, "bm73_premium_atomic_admin", role="admin")
    target = _user(db_session, "bm73_premium_atomic_target")
    status = premium_service.get_or_create_status(db_session, target)
    initial_balance = status.rubies_balance

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(premium_router.admin_service, "log_action", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.post(
            "/premium/grant",
            headers=_headers(admin, reason="Atomic premium regression"),
            json={"user_id": target.id, "amount": 25},
        )

    db_session.rollback()
    persisted = (
        db_session.query(models.PremiumStatus)
        .filter(models.PremiumStatus.user_id == target.id)
        .one()
    )
    assert persisted.rubies_balance == initial_balance


def test_season_start_rolls_back_when_audit_write_fails(
    client, db_session, monkeypatch
):
    admin = _user(db_session, "bm73_season_atomic", role="admin")
    world = db_session.query(models.World).first()
    before = db_session.query(models.Season).count()

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(season_router.admin_service, "log_action", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.post(
            "/season/start",
            headers=_headers(admin, reason="Atomic season regression"),
            json={"world_id": str(world.id), "name": "Atomic Season"},
        )

    db_session.rollback()
    assert db_session.query(models.Season).count() == before
