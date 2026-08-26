import pytest
from fastapi import HTTPException

from app import models, schemas
from app.services import community
from app.services.chat_manager import chat_manager


def _make_alliance_with_members(db_session, world, leader_user, member_user):
    alliance = models.Alliance(
        name="Community Test Alliance",
        description="",
        diplomacy="neutral",
        leader_id=leader_user.id,
        world_id=world.id,
    )
    db_session.add(alliance)
    db_session.flush()
    leader = models.AllianceMember(
        alliance_id=alliance.id,
        user_id=leader_user.id,
        rank=schemas.RANK_LEADER,
    )
    member = models.AllianceMember(
        alliance_id=alliance.id,
        user_id=member_user.id,
        rank=schemas.RANK_MEMBER,
    )
    db_session.add_all([leader, member])
    db_session.commit()
    db_session.refresh(alliance)
    db_session.refresh(leader)
    db_session.refresh(member)
    return alliance, leader, member


def test_rank_capabilities_are_explicit_and_leader_only_transfer():
    assert community.capabilities_for_rank(schemas.RANK_MEMBER) == frozenset()
    assert community.CAP_INVITE in community.capabilities_for_rank(schemas.RANK_GENERAL)
    assert community.CAP_DIPLOMACY in community.capabilities_for_rank(schemas.RANK_GENERAL)
    assert community.CAP_TRANSFER_LEADERSHIP not in community.capabilities_for_rank(
        schemas.RANK_GENERAL
    )
    assert community.capabilities_for_rank(schemas.RANK_LEADER) == community.ALL_CAPABILITIES


def test_require_capability_rejects_member():
    membership = models.AllianceMember(alliance_id=1, user_id=1, rank=schemas.RANK_MEMBER)
    with pytest.raises(HTTPException) as exc:
        community.require_capability(membership, community.CAP_INVITE)
    assert exc.value.status_code == 403


def test_transfer_leadership_is_atomic_and_updates_canonical_leader(
    db_session,
    user,
):
    world = db_session.query(models.World).first()
    target_user = models.User(
        username="community_target",
        email="community-target@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(target_user)
    db_session.flush()
    alliance, old_leader, target = _make_alliance_with_members(
        db_session,
        world,
        user,
        target_user,
    )

    transferred = community.transfer_leadership(
        db_session,
        alliance.id,
        user.id,
        target.id,
    )

    db_session.refresh(alliance)
    db_session.refresh(old_leader)
    assert alliance.leader_id == target_user.id
    assert transferred.id == target.id
    assert transferred.rank == schemas.RANK_LEADER
    assert old_leader.rank == schemas.RANK_GENERAL
    assert (
        db_session.query(models.AllianceMember)
        .filter(
            models.AllianceMember.alliance_id == alliance.id,
            models.AllianceMember.rank == schemas.RANK_LEADER,
        )
        .count()
        == 1
    )


def test_only_current_canonical_leader_can_transfer(db_session, user):
    world = db_session.query(models.World).first()
    target_user = models.User(
        username="community_general",
        email="community-general@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(target_user)
    db_session.flush()
    alliance, leader, target = _make_alliance_with_members(
        db_session,
        world,
        user,
        target_user,
    )
    target.rank = schemas.RANK_GENERAL
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        community.transfer_leadership(
            db_session,
            alliance.id,
            target_user.id,
            leader.id,
        )
    assert exc.value.status_code == 403


def test_transfer_rejects_member_from_another_alliance(db_session, user):
    world = db_session.query(models.World).first()
    target_user = models.User(
        username="community_outsider",
        email="community-outsider@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    third_user = models.User(
        username="community_third",
        email="community-third@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add_all([target_user, third_user])
    db_session.flush()
    alliance, _, _ = _make_alliance_with_members(db_session, world, user, target_user)

    other_alliance = models.Alliance(
        name="Other Community Alliance",
        leader_id=third_user.id,
        world_id=world.id,
    )
    db_session.add(other_alliance)
    db_session.flush()
    outsider = models.AllianceMember(
        alliance_id=other_alliance.id,
        user_id=third_user.id,
        rank=schemas.RANK_LEADER,
    )
    db_session.add(outsider)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        community.transfer_leadership(
            db_session,
            alliance.id,
            user.id,
            outsider.id,
        )
    assert exc.value.status_code == 404


def test_http_alliance_chat_uses_canonical_chat_message_store(db_session, user):
    world = db_session.query(models.World).first()
    member_user = models.User(
        username="community_chat_member",
        email="community-chat-member@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(member_user)
    db_session.flush()
    alliance, _, member = _make_alliance_with_members(
        db_session,
        world,
        user,
        member_user,
    )
    chat_manager.last_message_at.pop(member_user.id, None)

    message = community.post_alliance_chat_message(
        db_session,
        alliance.id,
        member_user,
        "  hola badword  ",
    )

    assert message.channel == "alliance"
    assert message.world_id == world.id
    assert message.alliance_id == alliance.id
    assert message.content == "hola ***"
    assert db_session.query(models.ChatMessage).filter_by(id=message.id).one()
    assert db_session.query(models.AllianceChatMessage).count() == 0

    history = community.list_alliance_chat_messages(
        db_session,
        alliance.id,
        user,
    )
    assert [entry.id for entry in history] == [message.id]

    db_session.delete(member)
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        community.list_alliance_chat_messages(
            db_session,
            alliance.id,
            member_user,
        )
    assert exc.value.status_code == 403


def test_alliance_chat_rejects_empty_and_oversized_content(db_session, user):
    world = db_session.query(models.World).first()
    member_user = models.User(
        username="community_chat_limits",
        email="community-chat-limits@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(member_user)
    db_session.flush()
    alliance, _, _ = _make_alliance_with_members(db_session, world, user, member_user)

    chat_manager.last_message_at.pop(member_user.id, None)
    with pytest.raises(HTTPException) as empty_exc:
        community.post_alliance_chat_message(db_session, alliance.id, member_user, "   ")
    assert empty_exc.value.status_code == 400

    chat_manager.last_message_at.pop(member_user.id, None)
    with pytest.raises(HTTPException) as long_exc:
        community.post_alliance_chat_message(
            db_session,
            alliance.id,
            member_user,
            "x" * (community.MAX_CHAT_MESSAGE_LENGTH + 1),
        )
    assert long_exc.value.status_code == 422
