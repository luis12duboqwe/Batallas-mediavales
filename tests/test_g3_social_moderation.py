from app import models
from app.routers.auth import create_access_token


def _headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


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


def _join(db_session, user: models.User, world: models.World) -> None:
    existing = (
        db_session.query(models.PlayerWorld)
        .filter_by(user_id=user.id, world_id=world.id)
        .one_or_none()
    )
    if existing is None:
        db_session.add(models.PlayerWorld(user_id=user.id, world_id=world.id))
        db_session.commit()


def test_private_message_requires_a_shared_world(client, db_session):
    world = db_session.query(models.World).first()
    foreign_world = models.World(name="Social foreign world", is_active=True)
    db_session.add(foreign_world)
    db_session.commit()
    db_session.refresh(foreign_world)

    sender = _create_user(db_session, "social_sender")
    receiver = _create_user(db_session, "social_receiver")
    _join(db_session, sender, world)
    _join(db_session, receiver, foreign_world)

    payload = {
        "receiver_id": receiver.id,
        "subject": "Hola",
        "content": "Mensaje de prueba",
    }
    denied = client.post("/message/send", headers=_headers(sender), json=payload)
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"] == "Players do not share a world"
    assert db_session.query(models.Message).count() == 0

    _join(db_session, receiver, world)
    allowed = client.post("/message/send", headers=_headers(sender), json=payload)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["sender_id"] == sender.id
    assert allowed.json()["receiver_id"] == receiver.id
    assert db_session.query(models.Message).count() == 1


def test_admin_can_freeze_unfreeze_and_read_audit_log(client, db_session):
    admin = _create_user(db_session, "moderator_admin", is_admin=True)
    target = _create_user(db_session, "moderated_player")
    target_token_before = _headers(target)
    initial_version = target.auth_version

    normal_logs = client.get("/admin/logs", headers=target_token_before)
    assert normal_logs.status_code == 403

    frozen = client.patch(
        f"/admin/user/{target.id}/freeze",
        headers=_headers(admin),
        json={"is_frozen": True, "reason": "manual moderation test"},
    )
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["is_frozen"] is True
    assert frozen.json()["freeze_reason"] == "manual moderation test"

    db_session.expire_all()
    target_after_freeze = db_session.query(models.User).filter_by(id=target.id).one()
    assert target_after_freeze.auth_version == initial_version + 1

    # The pre-moderation session is revoked by auth_version, before the freeze
    # state itself is even evaluated.
    old_session = client.get("/auth/me", headers=target_token_before)
    assert old_session.status_code == 401

    logs = client.get("/admin/logs", headers=_headers(admin), params={"limit": 20})
    assert logs.status_code == 200, logs.text
    freeze_entries = [entry for entry in logs.json() if entry["action"] == "set_user_freeze"]
    assert freeze_entries
    assert freeze_entries[0]["user_id"] == admin.id

    unfrozen = client.patch(
        f"/admin/user/{target.id}/freeze",
        headers=_headers(admin),
        json={"is_frozen": False},
    )
    assert unfrozen.status_code == 200, unfrozen.text
    assert unfrozen.json()["is_frozen"] is False
    assert unfrozen.json()["freeze_reason"] is None

    db_session.expire_all()
    target_after_unfreeze = db_session.query(models.User).filter_by(id=target.id).one()
    assert target_after_unfreeze.auth_version == initial_version + 2
    restored_session = client.get("/auth/me", headers=_headers(target_after_unfreeze))
    assert restored_session.status_code == 200, restored_session.text


def test_anticheat_review_is_admin_only_and_audited(client, db_session):
    admin = _create_user(db_session, "anticheat_admin", is_admin=True)
    player = _create_user(db_session, "flagged_player")
    flag = models.AntiCheatFlag(
        user_id=player.id,
        type_of_violation="test_violation",
        severity="high",
        details="deterministic moderation fixture",
    )
    db_session.add(flag)
    db_session.commit()
    db_session.refresh(flag)

    denied = client.get("/anticheat/flags", headers=_headers(player))
    assert denied.status_code == 403

    visible = client.get("/anticheat/flags", headers=_headers(admin))
    assert visible.status_code == 200, visible.text
    assert any(item["id"] == flag.id for item in visible.json())

    resolved = client.patch(
        f"/anticheat/resolve/{flag.id}",
        headers=_headers(admin),
        json={"resolved_status": "false_positive", "reviewed_by_admin": True},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolved_status"] == "false_positive"
    assert resolved.json()["reviewer_id"] == admin.id

    logs = client.get("/admin/logs", headers=_headers(admin), params={"limit": 50})
    assert logs.status_code == 200, logs.text
    moderation_entries = [
        entry for entry in logs.json() if entry["action"] == "resolve_anticheat_flag"
    ]
    assert moderation_entries
    assert moderation_entries[0]["user_id"] == admin.id
