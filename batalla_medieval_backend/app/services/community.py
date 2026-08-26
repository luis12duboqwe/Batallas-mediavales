from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas

CAP_INVITE = "alliance.invite"
CAP_MANAGE_MEMBERS = "alliance.manage_members"
CAP_TRANSFER_LEADERSHIP = "alliance.transfer_leadership"
CAP_EDIT = "alliance.edit"
CAP_DIPLOMACY = "alliance.diplomacy"
CAP_MASS_MESSAGE = "alliance.mass_message"
CAP_MODERATE_CHAT = "alliance.moderate_chat"
CAP_MODERATE_FORUM = "alliance.moderate_forum"

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
