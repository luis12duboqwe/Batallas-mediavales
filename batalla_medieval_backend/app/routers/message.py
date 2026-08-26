from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import notification as notification_service
from ..services import premium as premium_service
from ..services import social_privacy

router = APIRouter(tags=["message"])


def _active_world_id(db: Session, user: models.User) -> int:
    if user.world_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active world selected",
        )
    membership = (
        db.query(models.PlayerWorld.id)
        .filter(
            models.PlayerWorld.user_id == user.id,
            models.PlayerWorld.world_id == user.world_id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active world not joined",
        )
    return int(user.world_id)


def _user_in_world(db: Session, user_id: int, world_id: int) -> bool:
    return (
        db.query(models.PlayerWorld.id)
        .filter(
            models.PlayerWorld.user_id == user_id,
            models.PlayerWorld.world_id == world_id,
        )
        .first()
        is not None
    )


def _normalize_text(value: str, field: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} cannot be empty",
        )
    return normalized


def _scoped_message(
    db: Session,
    message_id: int,
    world_id: int,
) -> models.Message:
    message = (
        db.query(models.Message)
        .filter(
            models.Message.id == message_id,
            models.Message.world_id == world_id,
        )
        .first()
    )
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return message


@router.post("/send", response_model=schemas.MessageRead)
def send_message(
    payload: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    world_id = _active_world_id(db, current_user)
    receiver = db.query(models.User).filter(models.User.id == payload.receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found")
    if receiver.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot message yourself")
    if not _user_in_world(db, receiver.id, world_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Players do not share the active world",
        )
    if social_privacy.interaction_blocked(
        db,
        current_user.id,
        receiver.id,
        world_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Social interaction blocked",
        )

    receiver_status = premium_service.get_or_create_status(db, receiver)
    inbox_limit = premium_service.get_message_limit(receiver_status)
    inbox_query = db.query(models.Message).filter(
        models.Message.receiver_id == receiver.id,
        models.Message.world_id == world_id,
    )
    if inbox_query.count() >= inbox_limit:
        oldest = inbox_query.order_by(models.Message.timestamp.asc()).first()
        if oldest:
            db.delete(oldest)
            db.commit()

    premium_service.get_or_create_status(db, current_user)

    message = models.Message(
        sender_id=current_user.id,
        receiver_id=payload.receiver_id,
        world_id=world_id,
        subject=_normalize_text(payload.subject, "Subject"),
        content=_normalize_text(payload.content, "Content"),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    notification_service.create_notification(
        db,
        receiver,
        title="Nuevo mensaje privado",
        body=f"Has recibido un mensaje de {current_user.username}: {message.subject}",
        notification_type="message_received",
        allow_email=False,
    )
    return message


@router.get("/inbox", response_model=list[schemas.MessageRead])
def inbox(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    world_id = _active_world_id(db, current_user)
    return (
        db.query(models.Message)
        .filter(
            models.Message.receiver_id == current_user.id,
            models.Message.world_id == world_id,
        )
        .order_by(models.Message.timestamp.desc())
        .all()
    )


@router.get("/sent", response_model=list[schemas.MessageRead])
def sent_messages(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    world_id = _active_world_id(db, current_user)
    return (
        db.query(models.Message)
        .filter(
            models.Message.sender_id == current_user.id,
            models.Message.world_id == world_id,
        )
        .order_by(models.Message.timestamp.desc())
        .all()
    )


@router.get("/{message_id}", response_model=schemas.MessageRead)
def read_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    world_id = _active_world_id(db, current_user)
    message = _scoped_message(db, message_id, world_id)
    if current_user.id not in {message.sender_id, message.receiver_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this message")

    if not message.read and message.receiver_id == current_user.id:
        message.read = True
        db.commit()
        db.refresh(message)
    return message


@router.delete("/{message_id}")
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    world_id = _active_world_id(db, current_user)
    message = _scoped_message(db, message_id, world_id)
    if current_user.id not in {message.sender_id, message.receiver_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this message")

    db.delete(message)
    db.commit()
    return {"detail": "Message deleted"}
