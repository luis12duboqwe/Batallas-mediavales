from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..schemas import diplomacy as diplomacy_schema
from ..services import alliance as alliance_service
from ..services import community as community_service
from ..services import diplomacy as diplomacy_service
from ..services import social_privacy
from .world_access import require_world_access

router = APIRouter(tags=["alliance"])


def _resolve_world_id(current_user: models.User, world_id: int | None) -> int:
    resolved = world_id if world_id is not None else current_user.world_id
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active world selected",
        )
    return int(resolved)


def _require_alliance_world_access(
    db: Session,
    current_user: models.User,
    alliance_id: int,
) -> models.Alliance:
    alliance = alliance_service.get_alliance_or_404(db, alliance_id)
    require_world_access(alliance.world_id, db, current_user)
    return alliance


def _require_capability(
    db: Session,
    alliance_id: int,
    current_user: models.User,
    capability: str,
) -> models.AllianceMember:
    alliance = _require_alliance_world_access(db, current_user, alliance_id)
    membership = alliance_service.require_membership(db, alliance.id, current_user.id)
    return community_service.require_capability(membership, capability)


def _alliance_chat_read(message: models.ChatMessage) -> schemas.AllianceChatMessageRead:
    return schemas.AllianceChatMessageRead(
        id=message.id,
        alliance_id=message.alliance_id,
        user_id=message.user_id,
        username=message.user.username,
        message=message.content,
        created_at=message.timestamp,
    )


@router.get("/", response_model=Optional[schemas.AllianceRead])
def get_my_alliance(
    world_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resolved_world_id = _resolve_world_id(current_user, world_id)
    require_world_access(resolved_world_id, db, current_user)
    membership = alliance_service.get_membership_in_world(
        db,
        current_user.id,
        resolved_world_id,
    )
    return membership.alliance if membership else None


@router.post("/create", response_model=schemas.AllianceRead)
def create_alliance(
    payload: schemas.AllianceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return community_service.create_alliance_serialized(db, payload, current_user)


@router.get("/{alliance_id}/members", response_model=list[schemas.AllianceMemberPublic])
def list_alliance_members(
    alliance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_alliance_world_access(db, current_user, alliance_id)
    return alliance_service.list_members(db, alliance_id)


@router.post("/{alliance_id}/invite", response_model=schemas.AllianceInvitationRead)
def invite_player(
    alliance_id: int,
    payload: schemas.AllianceInvitationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    membership = _require_capability(
        db,
        alliance_id,
        current_user,
        community_service.CAP_INVITE,
    )
    target_user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if social_privacy.interaction_blocked(
        db,
        current_user.id,
        payload.user_id,
        membership.alliance.world_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Social interaction blocked",
        )
    return alliance_service.invite_member(db, alliance_id, current_user, payload.user_id)


@router.post("/invitations/{invitation_id}/accept", response_model=schemas.AllianceMemberRead)
def accept_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return alliance_service.accept_invitation(db, invitation_id, current_user)


@router.get("/invitations", response_model=list[schemas.AllianceInvitationRead])
def list_my_invitations(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_world_access(world_id, db, current_user)
    return alliance_service.get_user_invitations(db, current_user.id, world_id)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_alliance(
    world_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    resolved_world_id = _resolve_world_id(current_user, world_id)
    require_world_access(resolved_world_id, db, current_user)
    alliance_service.leave_alliance(db, current_user, resolved_world_id)


@router.post("/{alliance_id}/members/{member_id}/promote", response_model=schemas.AllianceMemberRead)
def promote_member(
    alliance_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_capability(db, alliance_id, current_user, community_service.CAP_MANAGE_MEMBERS)
    return alliance_service.promote_member(db, alliance_id, current_user, member_id)


@router.post("/{alliance_id}/members/{member_id}/demote", response_model=schemas.AllianceMemberRead)
def demote_member(
    alliance_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_capability(db, alliance_id, current_user, community_service.CAP_MANAGE_MEMBERS)
    return alliance_service.demote_member(db, alliance_id, current_user, member_id)


@router.delete("/{alliance_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def kick_member(
    alliance_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_capability(db, alliance_id, current_user, community_service.CAP_MANAGE_MEMBERS)
    alliance_service.kick_member(db, alliance_id, current_user, member_id)


@router.post(
    "/{alliance_id}/leadership/transfer",
    response_model=schemas.AllianceMemberRead,
)
def transfer_leadership(
    alliance_id: int,
    payload: schemas.AllianceLeadershipTransfer,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_capability(
        db,
        alliance_id,
        current_user,
        community_service.CAP_TRANSFER_LEADERSHIP,
    )
    return community_service.transfer_leadership(
        db,
        alliance_id,
        current_user.id,
        payload.target_member_id,
    )


@router.patch("/{alliance_id}", response_model=schemas.AllianceRead)
def update_alliance(
    alliance_id: int,
    payload: schemas.AllianceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_capability(db, alliance_id, current_user, community_service.CAP_EDIT)
    return alliance_service.update_alliance(db, alliance_id, current_user, payload)


@router.post("/{alliance_id}/chat", response_model=schemas.AllianceChatMessageRead)
def send_chat_message(
    alliance_id: int,
    payload: schemas.AllianceChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    message = community_service.post_alliance_chat_message(
        db,
        alliance_id,
        current_user,
        payload.message,
    )
    return _alliance_chat_read(message)


@router.get("/{alliance_id}/chat", response_model=list[schemas.AllianceChatMessageRead])
def list_chat_messages(
    alliance_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return [
        _alliance_chat_read(message)
        for message in community_service.list_alliance_chat_messages(
            db,
            alliance_id,
            current_user,
            limit=limit,
        )
    ]


@router.post("/{alliance_id}/mass-message")
def send_mass_message(
    alliance_id: int,
    payload: schemas.AllianceMassMessage,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_capability(db, alliance_id, current_user, community_service.CAP_MASS_MESSAGE)
    return alliance_service.send_mass_message(
        db,
        alliance_id,
        current_user,
        payload.subject,
        payload.content,
    )


@router.get("/{alliance_id}/diplomacy", response_model=list[diplomacy_schema.DiplomacyRead])
def get_diplomacy(
    alliance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_alliance_world_access(db, current_user, alliance_id)
    alliance_service.require_membership(db, alliance_id, current_user.id)
    return diplomacy_service.get_relations(db, alliance_id)


@router.post("/{alliance_id}/diplomacy", response_model=diplomacy_schema.DiplomacyRead)
def request_diplomacy(
    alliance_id: int,
    payload: diplomacy_schema.DiplomacyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_capability(db, alliance_id, current_user, community_service.CAP_DIPLOMACY)
    return diplomacy_service.request_relation(
        db,
        alliance_id,
        payload.alliance_target_id,
        payload.status,
    )


@router.post(
    "/{alliance_id}/diplomacy/{diplomacy_id}/accept",
    response_model=diplomacy_schema.DiplomacyRead,
)
def accept_diplomacy(
    alliance_id: int,
    diplomacy_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_capability(db, alliance_id, current_user, community_service.CAP_DIPLOMACY)
    return diplomacy_service.accept_relation(db, alliance_id, diplomacy_id)


@router.delete("/{alliance_id}/diplomacy/{diplomacy_id}")
def cancel_diplomacy(
    alliance_id: int,
    diplomacy_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_capability(db, alliance_id, current_user, community_service.CAP_DIPLOMACY)
    return diplomacy_service.cancel_relation(db, alliance_id, diplomacy_id)
