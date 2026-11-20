"""BM-0070: revocation of long-lived chat WebSocket send permissions."""

from datetime import timedelta

import pytest
from fastapi import WebSocketDisconnect

from app import models
from app.routers import chat as chat_router
from app.routers.auth import create_access_token
from app.services.chat_manager import chat_manager


def _join_selected_world(db_session, user):
    world = db_session.query(models.World).first()
    user.world_id = world.id
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=world.id))
    db_session.commit()
    return world


def _token(user):
    return create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )


@pytest.mark.parametrize(
    "revocation",
    ["freeze", "password_reset", "unverify", "switch_world", "remove_membership"],
)
def test_open_websocket_cannot_send_after_session_revocation(
    client, db_session, user, revocation
):
    world = _join_selected_world(db_session, user)
    token = _token(user)

    with client.websocket_connect(f"/chat/global?token={token}") as socket:
        if revocation == "freeze":
            user.is_frozen = True
        elif revocation == "password_reset":
            user.auth_version += 1
        elif revocation == "unverify":
            user.is_verified = False
        elif revocation == "switch_world":
            other_world = models.World(name="New selected world", is_active=True)
            db_session.add(other_world)
            db_session.flush()
            user.world_id = other_world.id
        elif revocation == "remove_membership":
            membership = (
                db_session.query(models.PlayerWorld)
                .filter_by(user_id=user.id, world_id=world.id)
                .one()
            )
            db_session.delete(membership)

        db_session.commit()
        socket.send_json({"content": "revoked socket must not persist this"})
        with pytest.raises(WebSocketDisconnect) as denied:
            socket.receive_json()
        assert denied.value.code == 1008

    assert db_session.query(models.ChatMessage).count() == 0
    assert not any(
        meta.get("user_id") == user.id for meta in chat_manager.connection_meta.values()
    )


def test_valid_websocket_session_can_still_send_and_receive(client, db_session, user):
    world = _join_selected_world(db_session, user)
    token = _token(user)
    chat_manager.last_message_at.clear()

    with client.websocket_connect(f"/chat/global?token={token}") as socket:
        socket.send_json({"content": "message from active session"})
        received = socket.receive_json()
        assert received["content"] == "message from active session"
        assert received["world_id"] == world.id
        assert received["user_id"] == user.id

    assert db_session.query(models.ChatMessage).count() == 1


def test_websocket_session_rejects_expired_or_wrong_purpose_token(db_session, user):
    world = _join_selected_world(db_session, user)

    expired = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version},
        expires_delta=timedelta(seconds=-1),
    )
    wrong_purpose = create_access_token(
        {"sub": user.username, "type": "reset", "ver": user.auth_version}
    )

    assert not chat_router._socket_session_is_valid(
        db_session, expired, user.id, world.id
    )
    assert not chat_router._socket_session_is_valid(
        db_session, wrong_purpose, user.id, world.id
    )
    assert chat_router._socket_session_is_valid(
        db_session, _token(user), user.id, world.id
    )
