from app import models
from app.routers.auth import create_access_token
from app.services import anticheat


def _headers(user: models.User, *, reason: str | None = None) -> dict[str, str]:
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )
    headers = {"Authorization": f"Bearer {token}"}
    if reason is not None:
        headers["X-Admin-Reason"] = reason
    return headers


def _user(db_session, username: str, *, admin: bool = False) -> models.User:
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
        is_admin=admin,
        admin_role="admin" if admin else None,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_critical_detection_never_freezes_or_revokes_session(client, db_session):
    player = _user(db_session, "bm74_critical_player")
    headers = _headers(player)
    initial_version = player.auth_version

    flag = anticheat.flag_violation(
        db_session,
        player,
        "fake_attack",
        "critical",
        "Impossible timing requires human review",
    )

    db_session.expire_all()
    persisted = db_session.query(models.User).filter_by(id=player.id).one()
    assert persisted.is_frozen is False
    assert persisted.freeze_reason is None
    assert persisted.auth_version == initial_version
    assert flag.resolved_status == "pending"
    assert flag.reviewed_by_admin is False
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_multiaccount_signal_never_sanctions_automatically(db_session):
    first = _user(db_session, "bm74_shared_ip_a")
    second = _user(db_session, "bm74_shared_ip_b")
    first.last_login_ip = "203.0.113.10"
    db_session.commit()

    anticheat.check_multiaccount_ip(db_session, second, "203.0.113.10")
    db_session.expire_all()
    persisted = db_session.query(models.User).filter_by(id=second.id).one()
    assert persisted.is_frozen is False
    flag = (
        db_session.query(models.AntiCheatFlag)
        .filter_by(user_id=second.id, type_of_violation="multiaccount_ip")
        .one()
    )
    assert flag.severity == "high"
    assert flag.resolved_status == "pending"


def test_distinct_evidence_is_not_collapsed_by_deduplication(db_session):
    player = _user(db_session, "bm74_distinct_evidence")
    first = anticheat.flag_violation(
        db_session,
        player,
        "fake_attack",
        "critical",
        "Impossible timing toward city 10",
    )
    second = anticheat.flag_violation(
        db_session,
        player,
        "fake_attack",
        "critical",
        "Impossible timing toward city 11",
    )
    duplicate = anticheat.flag_violation(
        db_session,
        player,
        "fake_attack",
        "critical",
        "Impossible timing toward city 11",
    )

    assert first.id != second.id
    assert duplicate.id == second.id
    assert (
        db_session.query(models.AntiCheatFlag)
        .filter_by(user_id=player.id, type_of_violation="fake_attack")
        .count()
        == 2
    )


def test_review_state_is_server_owned_and_reasoned(client, db_session):
    admin = _user(db_session, "bm74_review_admin", admin=True)
    player = _user(db_session, "bm74_review_player")
    flag = anticheat.flag_violation(
        db_session,
        player,
        "bot_detection",
        "high",
        "Review fixture",
    )

    invalid = client.patch(
        f"/anticheat/resolve/{flag.id}",
        headers=_headers(admin, reason="Invalid state probe"),
        json={"resolved_status": "auto_banned"},
    )
    assert invalid.status_code == 422, invalid.text

    reviewed = client.patch(
        f"/anticheat/resolve/{flag.id}",
        headers=_headers(admin, reason="Evidence does not support a violation"),
        json={"resolved_status": "false_positive", "reviewed_by_admin": False},
    )
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["reviewed_by_admin"] is True
    assert body["reviewer_id"] == admin.id
    assert body["reviewed_at"] is not None
    assert body["resolution_reason"] == "Evidence does not support a violation"


def test_flag_queue_supports_operational_filters_and_pagination(client, db_session):
    admin = _user(db_session, "bm74_filter_admin", admin=True)
    one = _user(db_session, "bm74_filter_one")
    two = _user(db_session, "bm74_filter_two")
    anticheat.flag_violation(db_session, one, "bot_detection", "critical", "one")
    anticheat.flag_violation(db_session, two, "multiaccount_ip", "high", "two")

    filtered = client.get(
        "/anticheat/flags",
        headers=_headers(admin),
        params={
            "user_id": one.id,
            "severity": "critical",
            "resolved_status": "pending",
            "limit": 10,
        },
    )
    assert filtered.status_code == 200, filtered.text
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["user_id"] == one.id

    first_page = client.get(
        "/anticheat/flags",
        headers=_headers(admin),
        params={"skip": 0, "limit": 1},
    )
    second_page = client.get(
        "/anticheat/flags",
        headers=_headers(admin),
        params={"skip": 1, "limit": 1},
    )
    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text
    assert len(first_page.json()) == 1
    assert len(second_page.json()) == 1
    assert first_page.json()[0]["id"] != second_page.json()[0]["id"]
