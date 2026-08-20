import asyncio

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
