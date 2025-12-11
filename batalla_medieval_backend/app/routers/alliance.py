from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import alliance as alliance_service

router = APIRouter(prefix="/alliance", tags=["alliance"])


@router.post("/create", response_model=schemas.AllianceRead)
def create_alliance(
    payload: schemas.AllianceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return alliance_service.create_alliance(db, payload, current_user)


@router.get("/{alliance_id}/members", response_model=list[schemas.AllianceMemberPublic])
def list_alliance_members(alliance_id: int, db: Session = Depends(get_db)):
    return alliance_service.list_members(db, alliance_id)


@router.post("/{alliance_id}/invite", response_model=schemas.AllianceInvitationRead)
def invite_player(
    alliance_id: int,
    payload: schemas.AllianceInvitationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    target_user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return alliance_service.invite_member(db, alliance_id, current_user, payload.user_id)


@router.post("/invitations/{invitation_id}/accept", response_model=schemas.AllianceMemberRead)
def accept_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return alliance_service.accept_invitation(db, invitation_id, current_user)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_alliance(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    alliance_service.leave_alliance(db, current_user)


@router.post("/{alliance_id}/members/{member_id}/promote", response_model=schemas.AllianceMemberRead)
def promote_member(
    alliance_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return alliance_service.promote_member(db, alliance_id, current_user, member_id)


@router.post("/{alliance_id}/members/{member_id}/demote", response_model=schemas.AllianceMemberRead)
def demote_member(
    alliance_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return alliance_service.demote_member(db, alliance_id, current_user, member_id)


@router.delete("/{alliance_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def kick_member(
    alliance_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    alliance_service.kick_member(db, alliance_id, current_user, member_id)


@router.patch("/{alliance_id}", response_model=schemas.AllianceRead)
def update_alliance(
    alliance_id: int,
    payload: schemas.AllianceUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return alliance_service.update_alliance(db, alliance_id, current_user, payload)


@router.post("/{alliance_id}/chat", response_model=schemas.AllianceChatMessageRead)
def send_chat_message(
    alliance_id: int,
    payload: schemas.AllianceChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    message = alliance_service.post_chat_message(db, alliance_id, current_user, payload)
    return schemas.AllianceChatMessageRead(
        id=message.id,
        alliance_id=message.alliance_id,
        user_id=message.user_id,
        username=message.user.username,
        message=message.message,
        created_at=message.created_at,
    )


@router.get("/{alliance_id}/chat", response_model=list[schemas.AllianceChatMessageRead])
def list_chat_messages(
    alliance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return alliance_service.list_chat_messages(db, alliance_id, current_user)
