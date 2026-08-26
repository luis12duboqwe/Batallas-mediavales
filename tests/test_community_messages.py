import pytest
from fastapi import HTTPException

from app import models, schemas
from app.routers import message as message_router
from app.services import alliance as alliance_service
from app.services import social_privacy


def _join(db_session, user_id, world_id):
    if not db_session.query(models.PlayerWorld).filter_by(user_id=user_id, world_id=world_id).first():
        db_session.add(models.PlayerWorld(user_id=user_id, world_id=world_id))
        db_session.commit()


def test_persistent_messages_are_scoped_to_active_world(db_session, user):
    world = db_session.query(models.World).first()
    other_world = models.World(
        name="Message Other World",
        speed_modifier=1.0,
        resource_modifier=1.0,
    )
    peer = models.User(
        username="message_peer",
        email="message-peer@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add_all([other_world, peer])
    db_session.commit()
    for world_id in (world.id, other_world.id):
        _join(db_session, user.id, world_id)
        _join(db_session, peer.id, world_id)

    user.world_id = world.id
    db_session.commit()
    first = message_router.send_message(
        schemas.MessageCreate(receiver_id=peer.id, subject="W1", content="Mensaje uno"),
        db_session,
        user,
    )
    assert first.world_id == world.id

    user.world_id = other_world.id
    db_session.commit()
    second = message_router.send_message(
        schemas.MessageCreate(receiver_id=peer.id, subject="W2", content="Mensaje dos"),
        db_session,
        user,
    )
    assert second.world_id == other_world.id

    sent_other_world = message_router.sent_messages(db_session, user)
    assert [row.id for row in sent_other_world] == [second.id]

    user.world_id = world.id
    db_session.commit()
    sent_first_world = message_router.sent_messages(db_session, user)
    assert [row.id for row in sent_first_world] == [first.id]


def test_block_prevents_new_persistent_message_in_that_world(db_session, user):
    world = db_session.query(models.World).first()
    peer = models.User(
        username="message_block_peer",
        email="message-block-peer@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(peer)
    db_session.commit()
    _join(db_session, user.id, world.id)
    _join(db_session, peer.id, world.id)
    user.world_id = world.id
    db_session.commit()

    social_privacy.block_user(db_session, peer.id, user.id, world.id)
    with pytest.raises(HTTPException) as exc:
        message_router.send_message(
            schemas.MessageCreate(
                receiver_id=peer.id,
                subject="Bloqueado",
                content="No debe enviarse",
            ),
            db_session,
            user,
        )
    assert exc.value.status_code == 403
    assert db_session.query(models.Message).count() == 0


def test_message_context_requires_selection_when_multiple_worlds_are_joined(
    db_session,
    user,
):
    first_world = db_session.query(models.World).first()
    second_world = models.World(
        name="Message Ambiguous World",
        speed_modifier=1.0,
        resource_modifier=1.0,
    )
    db_session.add(second_world)
    db_session.commit()
    _join(db_session, user.id, first_world.id)
    _join(db_session, user.id, second_world.id)
    user.world_id = None
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        message_router.sent_messages(db_session, user)
    assert exc.value.status_code == 400
    assert exc.value.detail == "No active world selected"


def test_alliance_mass_messages_are_persisted_in_alliance_world(db_session, user):
    world = db_session.query(models.World).first()
    peer = models.User(
        username="mass_message_peer",
        email="mass-message-peer@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(peer)
    db_session.flush()
    alliance = models.Alliance(
        name="Mass Message World Alliance",
        world_id=world.id,
        leader_id=user.id,
        diplomacy="neutral",
    )
    db_session.add(alliance)
    db_session.flush()
    db_session.add_all(
        [
            models.AllianceMember(alliance_id=alliance.id, user_id=user.id, rank=3),
            models.AllianceMember(alliance_id=alliance.id, user_id=peer.id, rank=1),
        ]
    )
    db_session.commit()

    result = alliance_service.send_mass_message(
        db_session,
        alliance.id,
        user,
        "Orden del día",
        "Defender el paso norte.",
    )

    assert result == {"count": 2}
    messages = db_session.query(models.Message).order_by(models.Message.id.asc()).all()
    assert len(messages) == 2
    assert {message.receiver_id for message in messages} == {user.id, peer.id}
    assert {message.world_id for message in messages} == {world.id}


def test_alliance_mass_message_schema_rejects_unbounded_payloads():
    with pytest.raises(Exception):
        schemas.AllianceMassMessage(subject="x" * 256, content="ok")
    with pytest.raises(Exception):
        schemas.AllianceMassMessage(subject="ok", content="x" * 10001)
