from datetime import timedelta

from app import models
from app.routers.auth import create_access_token
from app.services import admin_bot
from app.utils import utc_now


def _headers(user, *, reason=None):
    token = create_access_token({"sub": user.username, "ver": user.auth_version})
    headers = {"Authorization": f"Bearer {token}"}
    if reason is not None:
        headers["X-Admin-Reason"] = reason
    return headers


def test_admin_bot_report_does_not_delete_or_sanction_player_state(db_session):
    world = db_session.query(models.World).first()
    inactive = models.User(
        username="bm73_inactive_bot_target",
        email="bm73_inactive_bot_target@example.com",
        hashed_password="placeholder",
        is_verified=True,
        last_active_at=utc_now() - timedelta(days=120),
    )
    db_session.add(inactive)
    db_session.flush()

    old_audit = models.Log(
        user_id=inactive.id,
        action="legacy_audit_evidence",
        details="{}",
        timestamp=utc_now() - timedelta(days=180),
    )
    empty_alliance = models.Alliance(
        name="BM73 Empty Alliance",
        description="",
        diplomacy="neutral",
        leader_id=inactive.id,
        world_id=world.id,
    )
    severe_flag = models.AntiCheatFlag(
        user_id=inactive.id,
        type_of_violation="automation",
        severity="severe",
        details="{}",
    )
    db_session.add_all([old_audit, empty_alliance, severe_flag])
    db_session.commit()

    actions = admin_bot.run_admin_bot(db_session)
    db_session.commit()
    db_session.expire_all()

    preserved = db_session.query(models.User).filter_by(id=inactive.id).one()
    assert preserved.is_frozen is False
    assert db_session.query(models.Log).filter_by(id=old_audit.id).one() is not None
    assert db_session.query(models.Alliance).filter_by(id=empty_alliance.id).one() is not None
    assert db_session.query(models.AntiCheatFlag).filter_by(id=severe_flag.id).one().reviewed_by_admin is False
    assert all(action.startswith("Report-only:") for action in actions)
    assert db_session.query(models.AdminBotLog).filter_by(action="report_only_run").one() is not None


def test_admin_bot_run_requires_admin_capability_and_reason(client, db_session):
    admin = models.User(
        username="bm73_admin_bot_admin",
        email="bm73_admin_bot_admin@example.com",
        hashed_password="placeholder",
        is_verified=True,
        is_admin=True,
        admin_role="admin",
    )
    support = models.User(
        username="bm73_admin_bot_support",
        email="bm73_admin_bot_support@example.com",
        hashed_password="placeholder",
        is_verified=True,
        is_admin=True,
        admin_role="support",
    )
    db_session.add_all([admin, support])
    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(support)

    missing_reason = client.post("/admin_bot/run", headers=_headers(admin))
    assert missing_reason.status_code == 422, missing_reason.text

    forbidden = client.post(
        "/admin_bot/run",
        headers=_headers(support, reason="BM-0073 support must not run maintenance"),
    )
    assert forbidden.status_code == 403, forbidden.text

    allowed = client.post(
        "/admin_bot/run",
        headers=_headers(admin, reason="BM-0073 generate safe diagnostics"),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["detail"] == "Admin bot report generated"
    assert all(action.startswith("Report-only:") for action in allowed.json()["actions"])

    audit = (
        db_session.query(models.Log)
        .filter_by(user_id=admin.id, action="run_admin_bot_report")
        .one()
    )
    assert audit.reason == "BM-0073 generate safe diagnostics"
    assert audit.reversible is False
