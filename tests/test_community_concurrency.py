import threading

import pytest
from fastapi import HTTPException

from app import models
from app.database import SessionLocal, engine
from app.services import alliance as alliance_service
from app.services import diplomacy


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="BM-0070 community concurrency guarantees require PostgreSQL row locks",
)


def _run_pair(callable_factory):
    barrier = threading.Barrier(2)
    results = []
    errors = []
    lock = threading.Lock()

    def runner(index: int) -> None:
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            value = callable_factory(session, index)
            with lock:
                results.append(value)
        except Exception as exc:  # pragma: no cover - asserted below on PostgreSQL
            session.rollback()
            with lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=runner, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent BM-0070 operation did not finish"
    return results, errors


def test_concurrent_invitation_accept_creates_exactly_one_world_membership(db_session, user):
    world = db_session.query(models.World).first()
    inviter = models.User(
        username="community_concurrency_inviter",
        email="community-concurrency-inviter@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(inviter)
    db_session.flush()
    db_session.add_all(
        [
            models.PlayerWorld(user_id=user.id, world_id=world.id),
            models.PlayerWorld(user_id=inviter.id, world_id=world.id),
        ]
    )
    alliance = models.Alliance(
        name="Concurrent Invitation Alliance",
        world_id=world.id,
        leader_id=inviter.id,
        diplomacy="neutral",
    )
    db_session.add(alliance)
    db_session.flush()
    db_session.add(
        models.AllianceMember(
            alliance_id=alliance.id,
            user_id=inviter.id,
            rank=3,
        )
    )
    invitation = models.AllianceInvitation(
        alliance_id=alliance.id,
        invited_user_id=user.id,
        invited_by_id=inviter.id,
        status="pending",
    )
    db_session.add(invitation)
    db_session.commit()

    invitation_id = invitation.id
    user_id = user.id
    alliance_id = alliance.id

    def accept(session, _index):
        loaded_user = session.query(models.User).filter(models.User.id == user_id).one()
        membership = alliance_service.accept_invitation(session, invitation_id, loaded_user)
        return membership.id

    results, errors = _run_pair(accept)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], HTTPException)
    assert errors[0].status_code == 400

    db_session.expire_all()
    memberships = (
        db_session.query(models.AllianceMember)
        .join(models.Alliance, models.Alliance.id == models.AllianceMember.alliance_id)
        .filter(
            models.AllianceMember.user_id == user_id,
            models.Alliance.world_id == world.id,
        )
        .all()
    )
    assert len(memberships) == 1
    assert memberships[0].alliance_id == alliance_id
    refreshed_invitation = db_session.query(models.AllianceInvitation).filter_by(id=invitation_id).one()
    assert refreshed_invitation.status == "accepted"


def test_concurrent_reverse_diplomacy_creates_one_canonical_pair(db_session):
    world = db_session.query(models.World).first()
    alliance_a = models.Alliance(name="Concurrent Diplomacy A", world_id=world.id, diplomacy="neutral")
    alliance_b = models.Alliance(name="Concurrent Diplomacy B", world_id=world.id, diplomacy="neutral")
    db_session.add_all([alliance_a, alliance_b])
    db_session.commit()
    alliance_ids = (alliance_a.id, alliance_b.id)

    def request(session, index):
        source = alliance_ids[index]
        target = alliance_ids[1 - index]
        relation = diplomacy.request_relation(session, source, target, "nap")
        return relation.id

    results, errors = _run_pair(request)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], HTTPException)
    assert errors[0].status_code == 400

    db_session.expire_all()
    rows = (
        db_session.query(models.Diplomacy)
        .filter(
            ((models.Diplomacy.alliance_a_id == alliance_a.id) & (models.Diplomacy.alliance_b_id == alliance_b.id))
            | ((models.Diplomacy.alliance_a_id == alliance_b.id) & (models.Diplomacy.alliance_b_id == alliance_a.id))
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "pending_nap"
