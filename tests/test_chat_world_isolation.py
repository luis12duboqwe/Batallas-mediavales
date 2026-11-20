import asyncio

import pytest

from app import models
from app.routers.auth import create_access_token
from app.services.chat_manager import ChatManager


class DummySocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


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


def _create_user(db_session, username: str, world: models.World) -> models.User:
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
        world_id=world.id,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=world.id))
    db_session.commit()
    db_session.refresh(user)
    return user


def test_global_realtime_broadcast_is_partitioned_by_world():
    manager = ChatManager()
    world_one_socket = DummySocket()
    world_two_socket = DummySocket()

    manager.register_connection(
        world_one_socket,
        channel="global",
        user_id=1,
        world_id=101,
    )
    manager.register_connection(
        world_two_socket,
        channel="global",
        user_id=2,
        world_id=202,
    )

    payload = {"content": "solo mundo 101"}
    asyncio.run(
        manager.broadcast(
            channel="global",
            message=payload,
            sender_id=1,
            world_id=101,
        )
    )

    assert world_one_socket.messages == [payload]
    assert world_two_socket.messages == []
    assert manager.allow_message(1) is True
    assert manager.allow_message(1) is False


def test_chat_history_and_private_chat_respect_active_world(client, db_session):
    world_one = db_session.query(models.World).first()
    world_two = models.World(name="Chat foreign world", is_active=True)
    db_session.add(world_two)
    db_session.commit()
    db_session.refresh(world_two)

    viewer = _create_user(db_session, "chat_viewer", world_one)
    peer = _create_user(db_session, "chat_peer", world_one)
    foreign = _create_user(db_session, "chat_foreign", world_two)

    world_one_message = models.ChatMessage(
        user_id=peer.id,
        receiver_id=None,
        world_id=world_one.id,
        alliance_id=None,
        channel="global",
        content="visible",
    )
    world_two_message = models.ChatMessage(
        user_id=foreign.id,
        receiver_id=None,
        world_id=world_two.id,
        alliance_id=None,
        channel="global",
        content="hidden",
    )
    private_message = models.ChatMessage(
        user_id=peer.id,
        receiver_id=viewer.id,
        world_id=world_one.id,
        alliance_id=None,
        channel="private",
        content="private visible",
    )
    db_session.add_all([world_one_message, world_two_message, private_message])
    db_session.commit()

    history = client.get("/chat/history/global", headers=_headers(viewer))
    assert history.status_code == 200, history.text
    assert [item["content"] for item in history.json()] == ["visible"]

    private_history = client.get(f"/chat/private/{peer.id}", headers=_headers(viewer))
    assert private_history.status_code == 200, private_history.text
    assert [item["content"] for item in private_history.json()] == ["private visible"]

    foreign_history = client.get(f"/chat/private/{foreign.id}", headers=_headers(viewer))
    assert foreign_history.status_code == 403
    assert foreign_history.json()["detail"] == "Players do not share active world"


def test_private_realtime_broadcast_is_partitioned_by_world_and_user_pair():
    manager = ChatManager()
    alice_world_one = DummySocket()
    bob_world_one = DummySocket()
    alice_world_two = DummySocket()
    bob_world_two = DummySocket()
    unrelated_world_one = DummySocket()

    # The exact same two accounts can join multiple game worlds.
    for socket, user_id, world_id, peer_id in (
        (alice_world_one, 1, 101, 2),
        (bob_world_one, 2, 101, 1),
        (alice_world_two, 1, 202, 2),
        (bob_world_two, 2, 202, 1),
        (unrelated_world_one, 3, 101, 1),
    ):
        manager.register_connection(
            socket,
            channel="private",
            user_id=user_id,
            receiver_id=peer_id,
            world_id=world_id,
        )

    world_one_payload = {"content": "world 101 only"}
    asyncio.run(
        manager.broadcast(
            channel="private",
            message=world_one_payload,
            sender_id=1,
            receiver_id=2,
            world_id=101,
        )
    )
    assert alice_world_one.messages == [world_one_payload]
    assert bob_world_one.messages == [world_one_payload]
    assert alice_world_two.messages == []
    assert bob_world_two.messages == []
    assert unrelated_world_one.messages == []

    world_two_payload = {"content": "world 202 only"}
    asyncio.run(
        manager.broadcast(
            channel="private",
            message=world_two_payload,
            sender_id=2,
            receiver_id=1,
            world_id=202,
        )
    )
    assert alice_world_one.messages == [world_one_payload]
    assert bob_world_one.messages == [world_one_payload]
    assert alice_world_two.messages == [world_two_payload]
    assert bob_world_two.messages == [world_two_payload]

    # Disconnecting one world cannot unregister the other world's pair.
    manager.disconnect(alice_world_one)
    asyncio.run(
        manager.broadcast(
            channel="private",
            message={"content": "world 101 follow-up"},
            sender_id=2,
            receiver_id=1,
            world_id=101,
        )
    )
    assert alice_world_one.messages == [world_one_payload]
    assert bob_world_one.messages[-1]["content"] == "world 101 follow-up"
    assert alice_world_two.messages == [world_two_payload]
    assert bob_world_two.messages == [world_two_payload]


def test_private_realtime_channel_requires_explicit_world_scope():
    manager = ChatManager()
    socket = DummySocket()

    with pytest.raises(ValueError, match="scope metadata"):
        manager.register_connection(
            socket,
            channel="private",
            user_id=1,
            receiver_id=2,
        )

    assert manager.connection_meta == {}
    assert not manager.private_connections

    # A private broadcast missing world_id must never fall back to a
    # cross-world account pair.
    world_socket = DummySocket()
    manager.register_connection(
        world_socket,
        channel="private",
        user_id=1,
        receiver_id=2,
        world_id=101,
    )
    asyncio.run(
        manager.broadcast(
            channel="private",
            message={"content": "no world"},
            sender_id=1,
            receiver_id=2,
        )
    )
    assert world_socket.messages == []


def test_alliance_realtime_rechecks_current_recipients_after_member_is_kicked():
    manager = ChatManager()
    sender = DummySocket()
    continuing_member = DummySocket()
    kicked_member = DummySocket()
    foreign_world = DummySocket()

    for socket, user_id, world_id in (
        (sender, 1, 101),
        (continuing_member, 2, 101),
        (kicked_member, 3, 101),
        (foreign_world, 4, 202),
    ):
        manager.register_connection(
            socket,
            channel="alliance",
            user_id=user_id,
            world_id=world_id,
            alliance_id=55,
        )

    initial = {"content": "before kick"}
    asyncio.run(
        manager.broadcast(
            channel="alliance",
            message=initial,
            sender_id=1,
            world_id=101,
            alliance_id=55,
            authorized_user_ids={1, 2, 3},
        )
    )
    assert sender.messages == [initial]
    assert continuing_member.messages == [initial]
    assert kicked_member.messages == [initial]
    assert foreign_world.messages == []
    assert foreign_world not in manager.connection_meta

    after_kick = {"content": "after kick"}
    asyncio.run(
        manager.broadcast(
            channel="alliance",
            message=after_kick,
            sender_id=1,
            world_id=101,
            alliance_id=55,
            authorized_user_ids={1, 2},
        )
    )
    assert sender.messages[-1] == after_kick
    assert continuing_member.messages[-1] == after_kick
    assert kicked_member.messages == [initial]
    assert kicked_member not in manager.connection_meta
    assert kicked_member not in manager.alliance_connections[55]


def test_alliance_broadcast_fails_closed_without_current_membership_snapshot():
    manager = ChatManager()
    socket = DummySocket()
    manager.register_connection(
        socket,
        channel="alliance",
        user_id=10,
        world_id=101,
        alliance_id=55,
    )
    # Neither a missing authorization snapshot nor one for the wrong
    # world is permission to deliver an alliance message.
    asyncio.run(
        manager.broadcast(
            channel="alliance",
            message={"content": "missing recipients"},
            sender_id=10,
            alliance_id=55,
            world_id=101,
        )
    )
    assert socket.messages == []

    asyncio.run(
        manager.broadcast(
            channel="alliance",
            message={"content": "wrong world"},
            sender_id=10,
            alliance_id=55,
            world_id=202,
            authorized_user_ids={10},
        )
    )
    assert socket.messages == []
    assert socket not in manager.connection_meta
