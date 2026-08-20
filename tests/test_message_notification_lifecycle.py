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


def _create_user(db_session, username: str) -> models.User:
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _join(db_session, user: models.User, world: models.World) -> None:
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=world.id))
    db_session.commit()


def test_message_delivery_read_delete_and_notification_privacy(client, db_session):
    world = db_session.query(models.World).first()
    sender = _create_user(db_session, "message_sender")
    receiver = _create_user(db_session, "message_receiver")
    outsider = _create_user(db_session, "message_outsider")
    for user in (sender, receiver, outsider):
        _join(db_session, user, world)

    sent = client.post(
        "/message/send",
        headers=_headers(sender),
        json={
            "receiver_id": receiver.id,
            "subject": "Coordinación",
            "content": "Nos vemos en el mapa.",
        },
    )
    assert sent.status_code == 200, sent.text
    message_id = sent.json()["id"]
    assert sent.json()["read"] is False

    db_session.expire_all()
    notification = (
        db_session.query(models.Notification)
        .filter(
            models.Notification.user_id == receiver.id,
            models.Notification.type == "message_received",
        )
        .one()
    )

    receiver_inbox = client.get("/message/inbox", headers=_headers(receiver))
    assert receiver_inbox.status_code == 200, receiver_inbox.text
    assert [item["id"] for item in receiver_inbox.json()] == [message_id]

    sender_sent = client.get("/message/sent", headers=_headers(sender))
    assert sender_sent.status_code == 200, sender_sent.text
    assert [item["id"] for item in sender_sent.json()] == [message_id]

    outsider_inbox = client.get("/message/inbox", headers=_headers(outsider))
    assert outsider_inbox.status_code == 200
    assert outsider_inbox.json() == []

    outsider_read = client.get(f"/message/{message_id}", headers=_headers(outsider))
    assert outsider_read.status_code == 403
    outsider_delete = client.delete(f"/message/{message_id}", headers=_headers(outsider))
    assert outsider_delete.status_code == 403

    opened = client.get(f"/message/{message_id}", headers=_headers(receiver))
    assert opened.status_code == 200, opened.text
    assert opened.json()["read"] is True

    receiver_notifications = client.get("/notification/list", headers=_headers(receiver))
    assert receiver_notifications.status_code == 200, receiver_notifications.text
    receiver_notification_ids = [item["id"] for item in receiver_notifications.json()]
    assert notification.id in receiver_notification_ids

    outsider_notifications = client.get("/notification/list", headers=_headers(outsider))
    assert outsider_notifications.status_code == 200
    assert notification.id not in [item["id"] for item in outsider_notifications.json()]

    marked = client.patch(
        f"/notification/read/{notification.id}",
        headers=_headers(receiver),
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["read"] is True

    outsider_mark = client.patch(
        f"/notification/read/{notification.id}",
        headers=_headers(outsider),
    )
    assert outsider_mark.status_code == 404

    deleted = client.delete(f"/message/{message_id}", headers=_headers(receiver))
    assert deleted.status_code == 200, deleted.text
    assert db_session.query(models.Message).filter_by(id=message_id).one_or_none() is None
