from datetime import datetime, timezone
import threading

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app import models
from app.database import SessionLocal, engine
from app.services import alliance as alliance_service
from app.services import diplomacy


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


def test_invalid_private_message_does_not_evict_existing_inbox_message(
    db_session,
    user,
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
                subject="   ",
                content="Invalid after inbox limit check",
            ),
            db_session,
            user,
        )

    assert exc.value.status_code == 400
    assert db_session.query(models.Message).filter_by(id=oldest_id).one_or_none() is not None
    assert db_session.query(models.Message).filter_by(receiver_id=receiver.id).count() == 50


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

    invitation_check_barrier = threading.Barrier(2)
    successes = []
    errors = []
    result_lock = threading.Lock()

    def synchronize_empty_invitation_checks(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        normalized = statement.lower()
        if (
            "select" in normalized
            and "alliance_invitations" in normalized
            and "status" in normalized
        ):
            invitation_check_barrier.wait(timeout=5)

    event.listen(engine, "after_cursor_execute", synchronize_empty_invitation_checks)

    def invite():
        session = SessionLocal()
        try:
            actor = session.query(models.User).filter_by(id=user.id).one()
            alliance_service.invite_member(session, alliance.id, actor, target.id)
            with result_lock:
                successes.append(True)
        except Exception as exc:
            session.rollback()
            with result_lock:
                errors.append(exc)
        finally:
            session.close()

    try:
        threads = [threading.Thread(target=invite) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            assert not thread.is_alive(), "Concurrent invitation did not finish"
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_empty_invitation_checks)

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
