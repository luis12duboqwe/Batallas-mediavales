import pytest
from fastapi import HTTPException

from app import models
from app.services import social_privacy


def _join_world(db_session, user_id, world_id):
    existing = (
        db_session.query(models.PlayerWorld)
        .filter_by(user_id=user_id, world_id=world_id)
        .first()
    )
    if existing is None:
        db_session.add(models.PlayerWorld(user_id=user_id, world_id=world_id))
        db_session.commit()


def test_block_is_idempotent_symmetric_for_interaction_and_world_scoped(
    db_session,
    user,
):
    world = db_session.query(models.World).first()
    other_world = models.World(
        name="Privacy Other World",
        speed_modifier=1.0,
        resource_modifier=1.0,
    )
    peer = models.User(
        username="privacy_peer",
        email="privacy-peer@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add_all([other_world, peer])
    db_session.commit()
    _join_world(db_session, user.id, world.id)
    _join_world(db_session, peer.id, world.id)
    _join_world(db_session, user.id, other_world.id)
    _join_world(db_session, peer.id, other_world.id)

    first = social_privacy.block_user(db_session, user.id, peer.id, world.id)
    retry = social_privacy.block_user(db_session, user.id, peer.id, world.id)

    assert first.id == retry.id
    assert social_privacy.interaction_blocked(db_session, user.id, peer.id, world.id)
    assert social_privacy.interaction_blocked(db_session, peer.id, user.id, world.id)
    assert not social_privacy.interaction_blocked(
        db_session,
        user.id,
        peer.id,
        other_world.id,
    )
    assert db_session.query(models.UserBlock).count() == 1

    listed = social_privacy.list_blocks(db_session, user.id, world.id)
    assert [row.id for row in listed] == [first.id]

    social_privacy.unblock_user(db_session, user.id, peer.id, world.id)
    assert not social_privacy.interaction_blocked(db_session, user.id, peer.id, world.id)
    social_privacy.unblock_user(db_session, user.id, peer.id, world.id)


def test_block_requires_both_players_in_same_world(db_session, user):
    world = db_session.query(models.World).first()
    peer = models.User(
        username="privacy_not_joined",
        email="privacy-not-joined@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(peer)
    db_session.commit()
    _join_world(db_session, user.id, world.id)

    with pytest.raises(HTTPException) as exc:
        social_privacy.block_user(db_session, user.id, peer.id, world.id)
    assert exc.value.status_code == 403
    assert db_session.query(models.UserBlock).count() == 0


def test_user_cannot_block_self(db_session, user):
    world = db_session.query(models.World).first()
    _join_world(db_session, user.id, world.id)

    with pytest.raises(HTTPException) as exc:
        social_privacy.block_user(db_session, user.id, user.id, world.id)
    assert exc.value.status_code == 400
