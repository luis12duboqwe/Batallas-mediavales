from datetime import datetime
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas

RANK_MEMBER = schemas.RANK_MEMBER
RANK_GENERAL = schemas.RANK_GENERAL
RANK_LEADER = schemas.RANK_LEADER


def get_alliance_or_404(db: Session, alliance_id: int) -> models.Alliance:
    alliance = db.query(models.Alliance).filter(models.Alliance.id == alliance_id).first()
    if not alliance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alliance not found")
    return alliance


def get_membership(db: Session, alliance_id: int, user_id: int) -> models.AllianceMember | None:
    return (
        db.query(models.AllianceMember)
        .filter(models.AllianceMember.alliance_id == alliance_id, models.AllianceMember.user_id == user_id)
        .first()
    )


def require_membership(db: Session, alliance_id: int, user_id: int) -> models.AllianceMember:
    membership = get_membership(db, alliance_id, user_id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this alliance")
    return membership


def create_alliance(db: Session, payload: schemas.AllianceCreate, founder: models.User) -> models.Alliance:
    existing = db.query(models.Alliance).filter(models.Alliance.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Alliance name already used")

    alliance = models.Alliance(
        name=payload.name,
        description=payload.description,
        diplomacy="neutral",
        leader_id=founder.id,
    )
    db.add(alliance)
    db.commit()
    db.refresh(alliance)

    membership = models.AllianceMember(
        alliance_id=alliance.id, user_id=founder.id, rank=RANK_LEADER
    )
    db.add(membership)
    db.commit()
    from .achievement import update_achievement_progress

    update_achievement_progress(db, founder.id, "join_alliance", absolute_value=1)

    return alliance


def invite_member(
    db: Session, alliance_id: int, inviter: models.User, target_user_id: int
) -> models.AllianceInvitation:
    alliance = get_alliance_or_404(db, alliance_id)
    inviter_membership = require_membership(db, alliance_id, inviter.id)
    if inviter_membership.rank < RANK_GENERAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient rank to invite members")

    if db.query(models.AllianceMember).filter(models.AllianceMember.user_id == target_user_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already in an alliance")

    existing_invite = (
        db.query(models.AllianceInvitation)
        .filter(
            models.AllianceInvitation.alliance_id == alliance_id,
            models.AllianceInvitation.invited_user_id == target_user_id,
            models.AllianceInvitation.status == "pending",
        )
        .first()
    )
    if existing_invite:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pending invitation already exists")

    invitation = models.AllianceInvitation(
        alliance_id=alliance.id,
        invited_user_id=target_user_id,
        invited_by_id=inviter.id,
        status="pending",
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def accept_invitation(db: Session, invitation_id: int, user: models.User) -> models.AllianceMember:
    invitation = db.query(models.AllianceInvitation).filter(models.AllianceInvitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.invited_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invitation not for this user")
    if invitation.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation already processed")

    if db.query(models.AllianceMember).filter(models.AllianceMember.user_id == user.id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already in an alliance")

    membership = models.AllianceMember(
        alliance_id=invitation.alliance_id, user_id=user.id, rank=RANK_MEMBER
    )
    db.add(membership)
    invitation.status = "accepted"
    invitation.responded_at = datetime.utcnow()
    db.commit()
    db.refresh(membership)
    from .achievement import update_achievement_progress

    update_achievement_progress(db, user.id, "join_alliance", absolute_value=1)
    return membership


def leave_alliance(db: Session, user: models.User) -> None:
    membership = db.query(models.AllianceMember).filter(models.AllianceMember.user_id == user.id).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not part of an alliance")

    alliance = membership.alliance
    if membership.rank == RANK_LEADER:
        other_members = (
            db.query(models.AllianceMember)
            .filter(models.AllianceMember.alliance_id == alliance.id, models.AllianceMember.id != membership.id)
            .count()
        )
        if other_members:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Leader must transfer leadership before leaving",
            )
        alliance.leader_id = None
    db.delete(membership)
    db.commit()



def update_alliance(db: Session, alliance_id: int, actor: models.User, payload: schemas.AllianceUpdate) -> models.Alliance:
    alliance = get_alliance_or_404(db, alliance_id)
    actor_membership = require_membership(db, alliance_id, actor.id)
    if actor_membership.rank < RANK_GENERAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient rank to update alliance")

    if payload.description is not None:
        alliance.description = payload.description
    if payload.diplomacy is not None:
        alliance.diplomacy = payload.diplomacy

    db.commit()
    db.refresh(alliance)
    return alliance


def _require_management_rights(actor_membership: models.AllianceMember, target_membership: models.AllianceMember) -> None:
    if actor_membership.rank < RANK_GENERAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient rank for this action")
    if actor_membership.alliance_id != target_membership.alliance_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Members not in same alliance")
    if actor_membership.rank <= target_membership.rank:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage member of equal or higher rank")


def promote_member(db: Session, alliance_id: int, actor: models.User, target_member_id: int) -> models.AllianceMember:
    alliance = get_alliance_or_404(db, alliance_id)
    actor_membership = require_membership(db, alliance.id, actor.id)
    target_membership = (
        db.query(models.AllianceMember)
        .filter(models.AllianceMember.id == target_member_id, models.AllianceMember.alliance_id == alliance.id)
        .first()
    )
    if not target_membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    _require_management_rights(actor_membership, target_membership)

    if target_membership.rank >= RANK_GENERAL:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot promote beyond General")

    target_membership.rank += 1
    db.commit()
    db.refresh(target_membership)
    return target_membership


def demote_member(db: Session, alliance_id: int, actor: models.User, target_member_id: int) -> models.AllianceMember:
    alliance = get_alliance_or_404(db, alliance_id)
    actor_membership = require_membership(db, alliance.id, actor.id)
    target_membership = (
        db.query(models.AllianceMember)
        .filter(models.AllianceMember.id == target_member_id, models.AllianceMember.alliance_id == alliance.id)
        .first()
    )
    if not target_membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    _require_management_rights(actor_membership, target_membership)

    if target_membership.rank <= RANK_MEMBER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote below Member")

    target_membership.rank -= 1
    db.commit()
    db.refresh(target_membership)
    return target_membership


def kick_member(db: Session, alliance_id: int, actor: models.User, target_member_id: int) -> None:
    alliance = get_alliance_or_404(db, alliance_id)
    actor_membership = require_membership(db, alliance.id, actor.id)
    target_membership = (
        db.query(models.AllianceMember)
        .filter(models.AllianceMember.id == target_member_id, models.AllianceMember.alliance_id == alliance.id)
        .first()
    )
    if not target_membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    _require_management_rights(actor_membership, target_membership)

    db.delete(target_membership)
    db.commit()



def list_members(db: Session, alliance_id: int) -> List[schemas.AllianceMemberPublic]:
    alliance = get_alliance_or_404(db, alliance_id)
    memberships = (
        db.query(models.AllianceMember)
        .join(models.User, models.User.id == models.AllianceMember.user_id)
        .filter(models.AllianceMember.alliance_id == alliance.id)
        .all()
    )
    result: List[schemas.AllianceMemberPublic] = []
    for membership in memberships:
        result.append(
            schemas.AllianceMemberPublic(
                user_id=membership.user_id,
                username=membership.user.username,
                rank=membership.rank,
            )
        )
    return result


def post_chat_message(
    db: Session, alliance_id: int, author: models.User, payload: schemas.AllianceChatMessageCreate
) -> models.AllianceChatMessage:
    alliance = get_alliance_or_404(db, alliance_id)
    require_membership(db, alliance.id, author.id)
    message = models.AllianceChatMessage(
        alliance_id=alliance.id, user_id=author.id, message=payload.message
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_chat_messages(db: Session, alliance_id: int, viewer: models.User) -> List[schemas.AllianceChatMessageRead]:
    alliance = get_alliance_or_404(db, alliance_id)
    require_membership(db, alliance.id, viewer.id)
    messages = (
        db.query(models.AllianceChatMessage)
        .filter(models.AllianceChatMessage.alliance_id == alliance.id)
        .order_by(models.AllianceChatMessage.created_at.asc())
        .all()
    )
    result: List[schemas.AllianceChatMessageRead] = []
    for message in messages:
        result.append(
            schemas.AllianceChatMessageRead(
                id=message.id,
                alliance_id=message.alliance_id,
                user_id=message.user_id,
                username=message.user.username,
                message=message.message,
                created_at=message.created_at,
            )
        )
    return result
