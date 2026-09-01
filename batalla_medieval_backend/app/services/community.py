from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..utils import utc_now
from .chat_manager import chat_manager
from . import world_lifecycle

CAP_INVITE = "alliance.invite"
CAP_MANAGE_MEMBERS = "alliance.manage_members"
CAP_TRANSFER_LEADERSHIP = "alliance.transfer_leadership"
CAP_EDIT = "alliance.edit"
CAP_DIPLOMACY = "alliance.diplomacy"
CAP_MASS_MESSAGE = "alliance.mass_message"
CAP_MODERATE_CHAT = "alliance.moderate_chat"
CAP_MODERATE_FORUM = "alliance.moderate_forum"

MAX_CHAT_MESSAGE_LENGTH = 1000

ALL_CAPABILITIES = frozenset(
    {
        CAP_INVITE,
        CAP_MANAGE_MEMBERS,
        CAP_TRANSFER_LEADERSHIP,
        CAP_EDIT,
        CAP_DIPLOMACY,
        CAP_MASS_MESSAGE,
        CAP_MODERATE_CHAT,
        CAP_MODERATE_FORUM,
    }
)

GENERAL_CAPABILITIES = frozenset(
    {
        CAP_INVITE,
        CAP_MANAGE_MEMBERS,
        CAP_EDIT,
        CAP_DIPLOMACY,
        CAP_MASS_MESSAGE,
        CAP_MODERATE_CHAT,
        CAP_MODERATE_FORUM,
    }
)

RANK_CAPABILITIES = {
    schemas.RANK_MEMBER: frozenset(),
    schemas.RANK_GENERAL: GENERAL_CAPABILITIES,
    schemas.RANK_LEADER: ALL_CAPABILITIES,
}


def capabilities_for_rank(rank: int) -> frozenset[str]:
    return RANK_CAPABILITIES.get(int(rank), frozenset())


def has_capability(rank: int, capability: str) -> bool:
    return capability in capabilities_for_rank(rank)


def require_capability(
    membership: models.AllianceMember,
    capability: str,
) -> models.AllianceMember:
    if capability not in ALL_CAPABILITIES:
        raise ValueError(f"Unknown alliance capability: {capability}")
    if not has_capability(membership.rank, capability):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient alliance permission",
        )
    return membership


def create_alliance_serialized(
    db: Session,
    payload: schemas.AllianceCreate,
    founder: models.User,
) -> models.Alliance:
    """Serialize same-user alliance creation before delegating to legacy domain logic."""

    from . import alliance as alliance_service

    try:
        locked_founder = (
            db.query(models.User)
            .filter(models.User.id == founder.id)
            .with_for_update()
            .one()
        )
        return alliance_service.create_alliance(db, payload, locked_founder)
    except Exception:
        db.rollback()
        raise


def transfer_leadership(
    db: Session,
    alliance_id: int,
    actor_user_id: int,
    target_member_id: int,
) -> models.AllianceMember:
    """Atomically transfer leadership to another current alliance member.

    The alliance row serializes leadership changes. Membership rows are locked
    as well so a concurrent kick/demotion cannot invalidate the target between
    authorization and commit.
    """

    try:
        alliance = (
            db.query(models.Alliance)
            .filter(models.Alliance.id == alliance_id)
            .with_for_update()
            .one_or_none()
        )
        if alliance is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alliance not found",
            )

        memberships = (
            db.query(models.AllianceMember)
            .filter(models.AllianceMember.alliance_id == alliance_id)
            .order_by(models.AllianceMember.id.asc())
            .with_for_update()
            .all()
        )
        actor = next((row for row in memberships if row.user_id == actor_user_id), None)
        target = next((row for row in memberships if row.id == target_member_id), None)

        if actor is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this alliance",
            )
        require_capability(actor, CAP_TRANSFER_LEADERSHIP)

        if alliance.leader_id != actor_user_id or actor.rank != schemas.RANK_LEADER:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Alliance leadership state is inconsistent",
            )
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target member not found",
            )
        if target.id == actor.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Leadership already belongs to this member",
            )

        # Repair any legacy duplicate leader ranks inside the same serialized
        # transaction, then establish one canonical leader.
        for membership in memberships:
            if membership.id == target.id:
                membership.rank = schemas.RANK_LEADER
            elif membership.rank == schemas.RANK_LEADER:
                membership.rank = schemas.RANK_GENERAL
            db.add(membership)

        alliance.leader_id = target.user_id
        db.add(alliance)
        db.commit()
        db.refresh(target)
        return target
    except Exception:
        db.rollback()
        raise


def _current_membership(
    db: Session,
    alliance_id: int,
    user_id: int,
) -> models.AllianceMember:
    membership = (
        db.query(models.AllianceMember)
        .filter(
            models.AllianceMember.alliance_id == alliance_id,
            models.AllianceMember.user_id == user_id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this alliance",
        )
    return membership


def _normalize_chat_content(content: str) -> str:
    normalized = str(content).strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content required",
        )
    if len(normalized) > MAX_CHAT_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Message exceeds {MAX_CHAT_MESSAGE_LENGTH} characters",
        )
    return chat_manager.filter_content(normalized)


def post_alliance_chat_message(
    db: Session,
    alliance_id: int,
    author: models.User,
    content: str,
) -> models.ChatMessage:
    """Persist HTTP alliance chat in the same source of truth as WebSocket chat."""

    membership = _current_membership(db, alliance_id, author.id)
    alliance = membership.alliance
    world_lifecycle.require_world_open_http(db, alliance.world_id)
    if not chat_manager.allow_message(author.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )

    message = models.ChatMessage(
        user_id=author.id,
        world_id=alliance.world_id,
        alliance_id=alliance.id,
        channel="alliance",
        receiver_id=None,
        content=_normalize_chat_content(content),
        timestamp=utc_now(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_alliance_chat_messages(
    db: Session,
    alliance_id: int,
    viewer: models.User,
    *,
    limit: int = 100,
) -> list[models.ChatMessage]:
    """Read the canonical alliance chat only for a current member."""

    membership = _current_membership(db, alliance_id, viewer.id)
    alliance = membership.alliance
    safe_limit = max(1, min(int(limit), 100))
    messages = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.world_id == alliance.world_id,
            models.ChatMessage.alliance_id == alliance.id,
            models.ChatMessage.channel == "alliance",
        )
        .order_by(models.ChatMessage.timestamp.desc())
        .limit(safe_limit)
        .all()
    )
    return list(reversed(messages))
