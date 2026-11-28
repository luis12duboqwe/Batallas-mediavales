from datetime import datetime, timedelta, timezone
import threading

import pytest
from fastapi import HTTPException

from app import models
from app.database import SessionLocal, engine
from app.services import alliance as alliance_service
from app.services import diplomacy
from app.services import world_lifecycle


def _joined(db_session, user, world):
    db_session.add(models.PlayerWorld(user_id=user.id, world_id=world.id))


def _alliance(db_session, world, leader, *members):
    alliance = models.Alliance(
        name=f"G7 adversarial alliance {leader.id}",
        world_id=world.id,
        leader_id=leader.id,
        diplomacy="neutral",
    )
    db_session.add(alliance)
    db_session.flush()
    db_session.add(
        models.AllianceMember(
            alliance_id=alliance.id,
            user_id=leader.id,
            rank=3,
        )
    )
    for member in members:
        db_session.add(
            models.AllianceMember(
                alliance_id=alliance.id,
                user_id=member.id,
                rank=1,
            )
        )
    db_session.commit()
    db_session.refresh(alliance)
    return alliance


def test_diplomacy_cannot_be_cancelled_after_world_is_paused(db_session):
    world = db_session.query(models.World).first()
    alliance_a = models.Alliance(name="G7 cancel A", world_id=world.id)
    alliance_b = models.Alliance(name="G7 cancel B", world_id=world.id)
    db_session.add_all([alliance_a, alliance_b])
    db_session.commit()
    relation = diplomacy.request_relation(
        db_session,
        alliance_a.id,
        alliance_b.id,
        "ally",
    )
    relation = diplomacy.accept_relation(db_session, alliance_b.id, relation.id)

    world.lifecycle_status = "paused"
    world.is_active = False
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        diplomacy.cancel_relation(db_session, alliance_a.id, relation.id)

    assert exc.value.status_code == 409
    assert db_session.query(models.Diplomacy).filter_by(id=relation.id).one().status == "ally"


def test_alliance_invitation_is_rejected_when_world_is_paused(db_session, user):
    world = db_session.query(models.World).first()
    target = models.User(
        username="g7_paused_invitation_target",
        email="g7-paused-invitation-target@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(target)
    db_session.flush()
    _joined(db_session, user, world)
    _joined(db_session, target, world)
    alliance = _alliance(db_session, world, user)
    world.lifecycle_status = "paused"
    world.is_active = False
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        alliance_service.invite_member(db_session, alliance.id, user, target.id)

    assert exc.value.status_code == 409
    assert db_session.query(models.AllianceInvitation).count() == 0


def test_processed_invitation_conflict_is_a_domain_error_without_partial_write(
    db_session,
    user,
):
    world = db_session.query(models.World).first()
    target = models.User(
        username="g7_processed_invitation_target",
        email="g7-processed-invitation-target@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(target)
    db_session.flush()
    _joined(db_session, user, world)
    _joined(db_session, target, world)
    alliance = _alliance(db_session, world, user)
    invitation = models.AllianceInvitation(
        alliance_id=alliance.id,
        invited_user_id=target.id,
        invited_by_id=user.id,
        status="accepted",
    )
    db_session.add(invitation)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        alliance_service.invite_member(db_session, alliance.id, user, target.id)

    assert exc.value.status_code == 400
    assert (
        db_session.query(models.AllianceInvitation)
        .filter_by(alliance_id=alliance.id, invited_user_id=target.id)
        .count()
        == 1
    )


def test_alliance_mass_message_is_rejected_when_world_is_paused(db_session, user):
    world = db_session.query(models.World).first()
    member = models.User(
        username="g7_paused_mass_message_member",
        email="g7-paused-mass-message-member@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(member)
    db_session.flush()
    _joined(db_session, user, world)
    _joined(db_session, member, world)
    alliance = _alliance(db_session, world, user, member)
    world.lifecycle_status = "paused"
    world.is_active = False
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        alliance_service.send_mass_message(
            db_session,
            alliance.id,
            user,
            "G7 paused",
            "This should not be delivered",
        )

    assert exc.value.status_code == 409
    assert db_session.query(models.Message).count() == 0


def test_transfer_leadership_is_rejected_when_world_is_paused(db_session, user):
    from app.services import community as community_service

    world = db_session.query(models.World).first()
    target_user = models.User(
        username="g7_paused_transfer_target",
        email="g7-paused-transfer-target@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(target_user)
    db_session.flush()
    alliance = _alliance(db_session, world, user, target_user)
    target = (
        db_session.query(models.AllianceMember)
        .filter_by(alliance_id=alliance.id, user_id=target_user.id)
        .one()
    )
    world.lifecycle_status = "paused"
    world.is_active = False
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        community_service.transfer_leadership(
            db_session,
            alliance.id,
            user.id,
            target.id,
        )

    assert exc.value.status_code == 409
    db_session.refresh(alliance)
    assert alliance.leader_id == user.id


def test_mass_message_normalizes_and_respects_premium_inbox_limit_without_private_block_filter(
    db_session,
    user,
):
    from app.services import social_privacy

    world = db_session.query(models.World).first()
    peer = models.User(
        username="g7_mass_message_peer",
        email="g7-mass-message-peer@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(peer)
    db_session.flush()
    alliance = _alliance(db_session, world, user, peer)
    db_session.add_all(
        [
            models.Message(
                sender_id=user.id,
                receiver_id=peer.id,
                world_id=world.id,
                subject=f"Mass inbox {index}",
                content="Existing",
                timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc)
                + timedelta(days=index),
            )
            for index in range(50)
        ]
    )
    db_session.add(
        models.PremiumStatus(user_id=peer.id, increased_message_storage=True)
    )
    db_session.add(
        models.UserBlock(
            blocker_id=peer.id,
            blocked_id=user.id,
            world_id=world.id,
        )
    )
    db_session.commit()
    oldest_id = (
        db_session.query(models.Message.id)
        .filter_by(receiver_id=peer.id, world_id=world.id)
        .order_by(models.Message.timestamp.asc(), models.Message.id.asc())
        .first()[0]
    )

    result = alliance_service.send_mass_message(
        db_session,
        alliance.id,
        user,
        "  Council  ",
        "  Alliance-wide notice  ",
    )

    assert result == {"count": 2}
    peer_inbox = (
        db_session.query(models.Message)
        .filter_by(receiver_id=peer.id, world_id=world.id)
        .all()
    )
    assert len(peer_inbox) == 51
    assert oldest_id in {message.id for message in peer_inbox}
    assert any(
        message.subject == "[ALLIANCE] Council"
        and message.content == "Alliance-wide notice"
        for message in peer_inbox
    )
    assert social_privacy.interaction_blocked(db_session, user.id, peer.id, world.id)


def test_mass_message_rejects_whitespace_without_side_effects(db_session, user):
    world = db_session.query(models.World).first()
    alliance = _alliance(db_session, world, user)

    with pytest.raises(HTTPException) as exc:
        alliance_service.send_mass_message(
            db_session,
            alliance.id,
            user,
            "   ",
            "Content",
        )

    assert exc.value.status_code == 400
    assert db_session.query(models.Message).count() == 0
    assert db_session.query(models.Notification).count() == 0


@pytest.mark.parametrize(
    ("subject", "content"),
    [("   ", "Valid content"), ("Valid subject", "   ")],
)
def test_invalid_private_message_does_not_evict_existing_inbox_message(
    db_session,
    user,
    subject,
    content,
):
    from app import schemas
    from app.routers import message as message_router

    world = db_session.query(models.World).first()
    receiver = models.User(
        username="g7_message_receiver",
        email="g7-message-receiver@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(receiver)
    db_session.flush()
    _joined(db_session, user, world)
    _joined(db_session, receiver, world)
    user.world_id = world.id
    db_session.commit()
    oldest = models.Message(
        sender_id=user.id,
        receiver_id=receiver.id,
        world_id=world.id,
        subject="Keep this",
        content="Existing inbox message",
        timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(oldest)
    db_session.flush()
    db_session.add_all(
        [
            models.Message(
                sender_id=user.id,
                receiver_id=receiver.id,
                world_id=world.id,
                subject=f"Existing {index}",
                content="Existing inbox message",
            )
            for index in range(49)
        ]
    )
    db_session.commit()
    oldest_id = oldest.id

    with pytest.raises(HTTPException) as exc:
        message_router.send_message(
            schemas.MessageCreate(
                receiver_id=receiver.id,
                subject=subject,
                content=content,
            ),
            db_session,
            user,
        )

    assert exc.value.status_code == 400
    assert db_session.query(models.Message).filter_by(id=oldest_id).one_or_none() is not None
    assert db_session.query(models.Message).filter_by(receiver_id=receiver.id).count() == 50
    assert (
        db_session.query(models.PremiumStatus)
        .filter(models.PremiumStatus.user_id.in_((user.id, receiver.id)))
        .count()
        == 0
    )
    assert db_session.query(models.Notification).count() == 0


def test_valid_full_inbox_send_evicts_oldest_only_for_selected_world_and_recipient(
    db_session,
    user,
):
    from app import schemas
    from app.routers import message as message_router

    first_world = db_session.query(models.World).first()
    second_world = models.World(name="G7 full inbox second world")
    other_receiver = models.User(
        username="g7_other_receiver",
        email="g7-other-receiver@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    receiver = models.User(
        username="g7_full_inbox_receiver",
        email="g7-full-inbox-receiver@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add_all([second_world, other_receiver, receiver])
    db_session.flush()
    for member in (user, receiver, other_receiver):
        _joined(db_session, member, first_world)
    for member in (user, receiver, other_receiver):
        _joined(db_session, member, second_world)
    user.world_id = second_world.id
    db_session.commit()

    first_world_messages = [
        models.Message(
            sender_id=user.id,
            receiver_id=receiver.id,
            world_id=first_world.id,
            subject=f"First world {index}",
            content="Keep in the other world",
            timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc)
            + timedelta(days=index),
        )
        for index in range(50)
    ]
    second_world_messages = [
        models.Message(
            sender_id=user.id,
            receiver_id=receiver.id,
            world_id=second_world.id,
            subject=f"Second world {index}",
            content="Second world inbox",
            timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc)
            + timedelta(days=index),
        )
        for index in range(50)
    ]
    other_recipient_message = models.Message(
        sender_id=user.id,
        receiver_id=other_receiver.id,
        world_id=second_world.id,
        subject="Other recipient",
        content="Do not evict",
    )
    db_session.add_all([*first_world_messages, *second_world_messages, other_recipient_message])
    db_session.commit()
    first_world_ids = {row.id for row in first_world_messages}
    second_world_oldest_id = second_world_messages[0].id
    other_recipient_id = other_recipient_message.id

    sent = message_router.send_message(
        schemas.MessageCreate(
            receiver_id=receiver.id,
            subject="  Replacement  ",
            content="  Valid replacement  ",
        ),
        db_session,
        user,
    )

    assert sent.world_id == second_world.id
    assert sent.subject == "Replacement"
    assert sent.content == "Valid replacement"
    assert {
        row.id
        for row in db_session.query(models.Message)
        .filter_by(receiver_id=receiver.id, world_id=first_world.id)
        .all()
    } == first_world_ids
    second_world_inbox = (
        db_session.query(models.Message)
        .filter_by(receiver_id=receiver.id, world_id=second_world.id)
        .all()
    )
    assert len(second_world_inbox) == 50
    assert second_world_oldest_id not in {row.id for row in second_world_inbox}
    assert sent.id in {row.id for row in second_world_inbox}
    assert (
        db_session.query(models.Message)
        .filter_by(id=other_recipient_id)
        .one_or_none()
        is not None
    )


def test_failed_message_notification_rolls_back_inbox_eviction_and_insert(
    db_session,
    user,
    monkeypatch,
):
    from app import schemas
    from app.routers import message as message_router

    world = db_session.query(models.World).first()
    receiver = models.User(
        username="g7_rollback_receiver",
        email="g7-rollback-receiver@example.com",
        hashed_password="placeholder",
        is_verified=True,
        world_id=world.id,
    )
    db_session.add(receiver)
    db_session.flush()
    user.world_id = world.id
    _joined(db_session, user, world)
    _joined(db_session, receiver, world)
    db_session.add_all(
        [
            models.Message(
                sender_id=user.id,
                receiver_id=receiver.id,
                world_id=world.id,
                subject=f"Rollback {index}",
                content="Existing",
                timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc)
                + timedelta(days=index),
            )
            for index in range(50)
        ]
    )
    db_session.commit()
    oldest_id = (
        db_session.query(models.Message.id)
        .filter_by(receiver_id=receiver.id, world_id=world.id)
        .order_by(models.Message.timestamp.asc(), models.Message.id.asc())
        .first()[0]
    )

    def fail_commit():
        raise RuntimeError("notification persistence failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="notification persistence failed"):
        message_router.send_message(
            schemas.MessageCreate(
                receiver_id=receiver.id,
                subject="Atomic replacement",
                content="New message",
            ),
            db_session,
            user,
        )

    db_session.expire_all()
    assert (
        db_session.query(models.Message)
        .filter_by(id=oldest_id)
        .one_or_none()
        is not None
    )
    assert (
        db_session.query(models.Message)
        .filter_by(receiver_id=receiver.id, world_id=world.id)
        .count()
        == 50
    )
    assert db_session.query(models.Notification).count() == 0


def test_notification_dispatch_failure_does_not_turn_committed_send_into_error(
    db_session,
    user,
    monkeypatch,
):
    from app import schemas
    from app.routers import message as message_router

    world = db_session.query(models.World).first()
    receiver = models.User(
        username="g7_dispatch_failure_receiver",
        email="g7-dispatch-failure-receiver@example.com",
        hashed_password="placeholder",
        is_verified=True,
        world_id=world.id,
    )
    db_session.add(receiver)
    db_session.flush()
    user.world_id = world.id
    _joined(db_session, user, world)
    _joined(db_session, receiver, world)
    db_session.commit()

    async def fail_notification(*args, **kwargs):
        raise RuntimeError("socket unavailable")

    monkeypatch.setattr(
        message_router.socket_manager,
        "notify_user",
        fail_notification,
    )
    sent = message_router.send_message(
        schemas.MessageCreate(
            receiver_id=receiver.id,
            subject="Committed delivery",
            content="Realtime is best effort",
        ),
        db_session,
        user,
    )

    assert sent.subject == "Committed delivery"
    assert db_session.query(models.Message).filter_by(id=sent.id).one()
    assert (
        db_session.query(models.Notification)
        .filter_by(user_id=receiver.id, type="message_received")
        .count()
        == 1
    )


def test_private_websocket_revalidates_recipient_world_and_privacy_per_send(
    client,
    db_session,
    user,
):
    from app.routers.auth import create_access_token

    world = db_session.query(models.World).first()
    receiver = models.User(
        username="g7_socket_private_receiver",
        email="g7-socket-private-receiver@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(receiver)
    db_session.flush()
    user.world_id = world.id
    _joined(db_session, user, world)
    _joined(db_session, receiver, world)
    db_session.commit()
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )

    with client.websocket_connect(
        f"/chat/private?token={token}&receiver_id={receiver.id}"
    ) as socket:
        db_session.query(models.PlayerWorld).filter_by(
            user_id=receiver.id,
            world_id=world.id,
        ).delete()
        db_session.commit()
        socket.send_json({"content": "not delivered across worlds"})
        assert socket.receive_json()["error"] == "Private interaction blocked"

    assert db_session.query(models.ChatMessage).count() == 0


def test_existing_websocket_rejects_paused_world_and_resumes_after_reopen(
    client,
    db_session,
    user,
):
    from app.routers.auth import create_access_token
    from app.services.chat_manager import chat_manager

    world = db_session.query(models.World).first()
    world.is_active = True
    world.lifecycle_status = "open"
    user.world_id = world.id
    _joined(db_session, user, world)
    db_session.commit()
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )
    chat_manager.last_message_at.pop(user.id, None)

    with client.websocket_connect(f"/chat/global?token={token}") as socket:
        world.lifecycle_status = "paused"
        world.is_active = False
        db_session.commit()
        socket.send_json({"content": "blocked while paused"})
        assert socket.receive_json()["error"] == "World is not open"
        assert db_session.query(models.ChatMessage).count() == 0

        world.lifecycle_status = "open"
        world.is_active = True
        db_session.commit()
        socket.send_json({"content": "accepted after reopen"})
        assert socket.receive_json()["content"] == "accepted after reopen"

    messages = db_session.query(models.ChatMessage).all()
    assert len(messages) == 1
    assert messages[0].content == "accepted after reopen"


@pytest.mark.parametrize("lifecycle_status", ["closed", "archived"])
def test_existing_websocket_cannot_write_closed_or_archived_world(
    client,
    db_session,
    user,
    lifecycle_status,
):
    from app.routers.auth import create_access_token

    world = db_session.query(models.World).first()
    world.is_active = True
    world.lifecycle_status = "open"
    user.world_id = world.id
    _joined(db_session, user, world)
    db_session.commit()
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )

    with client.websocket_connect(f"/chat/global?token={token}") as socket:
        world.lifecycle_status = lifecycle_status
        world.is_active = False
        db_session.commit()
        socket.send_json({"content": "not written"})
        assert socket.receive_json()["error"] == "World is not open"

    assert db_session.query(models.ChatMessage).count() == 0


@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="World lifecycle row-lock validation requires PostgreSQL",
)
def test_pause_serializes_with_leadership_transfer_and_rejects_after_pause(
    db_session,
    user,
):
    from app.services import community as community_service

    world = db_session.query(models.World).first()
    target_user = models.User(
        username="g7_transfer_pause_target",
        email="g7-transfer-pause-target@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(target_user)
    db_session.flush()
    alliance = _alliance(db_session, world, user, target_user)
    target = (
        db_session.query(models.AllianceMember)
        .filter_by(alliance_id=alliance.id, user_id=target_user.id)
        .one()
    )
    world_lifecycle.require_world_open(db_session, world.id, lock=True)

    gate_query_started = threading.Event()
    results = []

    def observe_gate_query(connection, cursor, statement, parameters, context, executemany):
        if (
            threading.current_thread().name == "g7-transfer-writer"
            and "worlds" in statement.lower()
            and "for update" in statement.lower()
        ):
            gate_query_started.set()

    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", observe_gate_query)

    def transfer_after_pause_gate():
        session = SessionLocal()
        try:
            community_service.transfer_leadership(
                session,
                alliance.id,
                user.id,
                target.id,
            )
            results.append("transferred")
        except HTTPException as exc:
            session.rollback()
            results.append(exc.status_code)
        finally:
            session.close()

    writer = threading.Thread(target=transfer_after_pause_gate, name="g7-transfer-writer")
    try:
        writer.start()
        assert gate_query_started.wait(timeout=5)
        db_session.refresh(world)
        world.lifecycle_status = "paused"
        world.is_active = False
        db_session.commit()
        writer.join(timeout=10)
        assert not writer.is_alive(), "Leadership transfer remained blocked after pause"
    finally:
        event.remove(engine, "before_cursor_execute", observe_gate_query)

    assert results == [409]
    db_session.refresh(alliance)
    assert alliance.leader_id == user.id


@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="World lifecycle row-lock validation requires PostgreSQL",
)
def test_pause_serializes_with_invitation_and_rejects_after_pause(db_session, user):
    world = db_session.query(models.World).first()
    target = models.User(
        username="g7_pause_race_target",
        email="g7-pause-race-target@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(target)
    db_session.flush()
    _joined(db_session, user, world)
    _joined(db_session, target, world)
    alliance = _alliance(db_session, world, user)
    world_lifecycle.require_world_open(db_session, world.id, lock=True)

    gate_query_started = threading.Event()
    results = []

    def observe_gate_query(connection, cursor, statement, parameters, context, executemany):
        if (
            threading.current_thread().name == "g7-invitation-writer"
            and "worlds" in statement.lower()
            and "for update" in statement.lower()
        ):
            gate_query_started.set()

    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", observe_gate_query)

    def invite_after_pause_gate():
        session = SessionLocal()
        try:
            actor = session.query(models.User).filter_by(id=user.id).one()
            alliance_service.invite_member(session, alliance.id, actor, target.id)
            results.append("created")
        except HTTPException as exc:
            session.rollback()
            results.append(exc.status_code)
        finally:
            session.close()

    writer = threading.Thread(target=invite_after_pause_gate, name="g7-invitation-writer")
    try:
        writer.start()
        assert gate_query_started.wait(timeout=5)
        db_session.refresh(world)
        world.lifecycle_status = "paused"
        world.is_active = False
        db_session.commit()
        writer.join(timeout=10)
        assert not writer.is_alive(), "Invitation writer remained blocked after pause"
    finally:
        event.remove(engine, "before_cursor_execute", observe_gate_query)

    assert results == [409]
    assert db_session.query(models.AllianceInvitation).count() == 0


@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Concurrent inbox serialization requires PostgreSQL row locks",
)
def test_concurrent_full_inbox_sends_keep_limit_and_both_deliveries(
    db_session,
    user,
):
    from app import schemas
    from app.routers import message as message_router

    world = db_session.query(models.World).first()
    sender_two = models.User(
        username="g7_concurrent_sender_two",
        email="g7-concurrent-sender-two@example.com",
        hashed_password="placeholder",
        is_verified=True,
        world_id=world.id,
    )
    receiver = models.User(
        username="g7_concurrent_receiver",
        email="g7-concurrent-receiver@example.com",
        hashed_password="placeholder",
        is_verified=True,
        world_id=world.id,
    )
    db_session.add_all([sender_two, receiver])
    db_session.flush()
    user.world_id = world.id
    for member in (user, sender_two, receiver):
        _joined(db_session, member, world)
    db_session.add_all(
        [
            models.Message(
                sender_id=user.id,
                receiver_id=receiver.id,
                world_id=world.id,
                subject=f"Concurrent inbox {index}",
                content="Existing",
                timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc)
                + timedelta(days=index),
            )
            for index in range(50)
        ]
    )
    db_session.commit()

    sender_ids = (user.id, sender_two.id)
    receiver_id = receiver.id
    start_barrier = threading.Barrier(2)
    successes = []
    errors = []
    result_lock = threading.Lock()

    def send(index):
        session = SessionLocal()
        try:
            sender = session.query(models.User).filter_by(id=sender_ids[index]).one()
            start_barrier.wait(timeout=5)
            message = message_router.send_message(
                schemas.MessageCreate(
                    receiver_id=receiver_id,
                    subject=f"Concurrent send {index}",
                    content="Valid concurrent content",
                ),
                session,
                sender,
            )
            with result_lock:
                successes.append(message.id)
        except Exception as exc:
            session.rollback()
            with result_lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=send, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), "Concurrent inbox send did not finish"

    assert len(successes) == 2
    assert errors == []
    db_session.expire_all()
    inbox = (
        db_session.query(models.Message)
        .filter_by(receiver_id=receiver.id, world_id=world.id)
        .all()
    )
    assert len(inbox) == 50
    assert set(successes).issubset({row.id for row in inbox})


@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Concurrent invitation serialization requires PostgreSQL",
)
def test_concurrent_duplicate_invitations_return_one_domain_conflict(db_session, user):
    world = db_session.query(models.World).first()
    target = models.User(
        username="g7_duplicate_invitation_target",
        email="g7-duplicate-invitation-target@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(target)
    db_session.flush()
    _joined(db_session, user, world)
    _joined(db_session, target, world)
    alliance = _alliance(db_session, world, user)
    db_session.commit()

    start_barrier = threading.Barrier(2)
    successes = []
    errors = []
    result_lock = threading.Lock()

    def invite():
        session = SessionLocal()
        try:
            actor = session.query(models.User).filter_by(id=user.id).one()
            start_barrier.wait(timeout=5)
            alliance_service.invite_member(session, alliance.id, actor, target.id)
            with result_lock:
                successes.append(True)
        except Exception as exc:
            session.rollback()
            with result_lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=invite) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent invitation did not finish"

    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], HTTPException)
    assert errors[0].status_code == 400
    assert (
        db_session.query(models.AllianceInvitation)
        .filter_by(alliance_id=alliance.id, invited_user_id=target.id)
        .count()
        == 1
    )
