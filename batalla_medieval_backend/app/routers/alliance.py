from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import alliance as alliance_service

router = APIRouter(tags=["alliance"])


@router.get("/", response_model=Optional[schemas.AllianceRead])
def get_my_alliance(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    membership = db.query(models.AllianceMember).filter(models.AllianceMember.user_id == current_user.id).first()
    if not membership:
        return None
    return membership.alliance


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


@router.get("/invitations", response_model=list[schemas.AllianceInvitationRead])
def list_my_invitations(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return alliance_service.get_user_invitations(db, current_user.id, world_id)


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


@router.post("/{alliance_id}/diplomacy", response_model=schemas.DiplomacyRead)
def propose_diplomacy(
    alliance_id: int,
    payload: schemas.DiplomacyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Propose a diplomatic relation (War, NAP, Alliance)."""
    # Verify user is leader/general of alliance_id
    membership = alliance_service.require_membership(db, alliance_id, current_user.id)
    if membership.rank < schemas.RANK_GENERAL:
        raise HTTPException(status_code=403, detail="Insufficient rank")
        
    # Check if target alliance exists
    target = alliance_service.get_alliance_or_404(db, payload.alliance_target_id)
    if target.world_id != membership.alliance.world_id:
        raise HTTPException(status_code=400, detail="Target alliance in different world")
        
    # Create or update diplomacy
    # Logic:
    # If War -> Immediate
    # If NAP/Ally -> Pending until accepted? Or immediate for now?
    # Let's implement immediate for War, pending for others.
    
    # For simplicity in this iteration, we just create the record.
    # In a real game, we'd need a "request" system for NAP/Ally.
    # Here we assume "War" is unilateral, others might need acceptance.
    
    # Check existing
    existing = db.query(models.Diplomacy).filter(
        ((models.Diplomacy.alliance_a_id == alliance_id) & (models.Diplomacy.alliance_b_id == target.id)) |
        ((models.Diplomacy.alliance_a_id == target.id) & (models.Diplomacy.alliance_b_id == alliance_id))
    ).first()
    
    if existing:
        existing.status = payload.status
        db.commit()
        db.refresh(existing)
        return existing
        
    diplomacy = models.Diplomacy(
        alliance_a_id=alliance_id,
        alliance_b_id=target.id,
        status=payload.status
    )
    db.add(diplomacy)
    db.commit()
    db.refresh(diplomacy)
    return diplomacy

@router.get("/{alliance_id}/diplomacy", response_model=list[schemas.DiplomacyRead])
def list_diplomacy(
    alliance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    alliance_service.require_membership(db, alliance_id, current_user.id)
    return db.query(models.Diplomacy).filter(
        (models.Diplomacy.alliance_a_id == alliance_id) | (models.Diplomacy.alliance_b_id == alliance_id)
    ).all()

@router.post("/{alliance_id}/mass-message")
def send_mass_message(
    alliance_id: int,
    payload: schemas.AllianceMassMessage,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return alliance_service.send_mass_message(db, alliance_id, current_user, payload.subject, payload.content)

from ..services import diplomacy as diplomacy_service
from ..schemas import diplomacy as diplomacy_schema

@router.get("/{alliance_id}/diplomacy", response_model=list[diplomacy_schema.DiplomacyRead])
def get_diplomacy(
    alliance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Check if user is member of alliance? Or is it public?
    # Usually diplomacy is public or at least visible to members.
    # Let's allow members for now.
    alliance_service.require_membership(db, alliance_id, current_user.id)
    return diplomacy_service.get_relations(db, alliance_id)

@router.post("/{alliance_id}/diplomacy", response_model=diplomacy_schema.DiplomacyRead)
def request_diplomacy(
    alliance_id: int,
    payload: diplomacy_schema.DiplomacyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    membership = alliance_service.require_membership(db, alliance_id, current_user.id)
    if membership.rank < alliance_service.RANK_GENERAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient rank")
        
    return diplomacy_service.request_relation(db, alliance_id, payload.alliance_target_id, payload.status)

@router.post("/{alliance_id}/diplomacy/{diplomacy_id}/accept", response_model=diplomacy_schema.DiplomacyRead)
def accept_diplomacy(
    alliance_id: int,
    diplomacy_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    membership = alliance_service.require_membership(db, alliance_id, current_user.id)
    if membership.rank < alliance_service.RANK_GENERAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient rank")
        
    return diplomacy_service.accept_relation(db, alliance_id, diplomacy_id)

@router.delete("/{alliance_id}/diplomacy/{diplomacy_id}")
def cancel_diplomacy(
    alliance_id: int,
    diplomacy_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    membership = alliance_service.require_membership(db, alliance_id, current_user.id)
    if membership.rank < alliance_service.RANK_GENERAL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient rank")
        
    return diplomacy_service.cancel_relation(db, alliance_id, diplomacy_id)
