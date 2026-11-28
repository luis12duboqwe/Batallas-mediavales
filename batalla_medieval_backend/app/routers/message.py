import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import premium as premium_service
from ..services import social_privacy, socket_manager, world_lifecycle

router = APIRouter(tags=["message"])


def _active_world_id(db: Session, user: models.User) -> int:
    """Resolve the unambiguous social world for persistent messaging.

    Normal gameplay uses ``user.world_id``. Legacy/test users that have joined
    exactly one world but have not selected it explicitly are also safe to
    resolve because no cross-world choice exists. Multiple joined worlds still
    require an explicit active selection.
    """

    if user.world_id is not None:
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

    joined_worlds = [
        int(world_id)
        for (world_id,) in (
            db.query(models.PlayerWorld.world_id)
            .filter(models.PlayerWorld.user_id == user.id)
            .order_by(models.PlayerWorld.world_id.asc())
            .all()
        )
    ]
    if len(joined_worlds) == 1:
        return joined_worlds[0]
    if not joined_worlds:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Player has not joined a world",
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No active world selected",
    )


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
    subject = _normalize_text(payload.subject, "Subject")
    content = _normalize_text(payload.content, "Content")
    world_id = _active_world_id(db, current_user)
    try:
        world_lifecycle.require_world_open(db, world_id, lock=False)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="World is not open") from exc
    receiver = db.query(models.User).filter(models.User.id == payload.receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found")
    if receiver.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot message yourself")
    if not _user_in_world(db, receiver.id, world_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Players do not share a world",
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

    try:
        world_lifecycle.require_world_open(db, world_id, lock=True)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="World is not open") from exc

    locked_users = (
        db.query(models.User)
        .filter(models.User.id.in_((current_user.id, receiver.id)))
        .order_by(models.User.id.asc())
        .with_for_update()
        .populate_existing()
        .all()
    )
    users_by_id = {user.id: user for user in locked_users}
    sender = users_by_id.get(current_user.id)
    receiver = users_by_id.get(receiver.id)
    if sender is None or receiver is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if _active_world_id(db, sender) != world_id:
        raise HTTPException(status_code=409, detail="Active world changed")
    if not _user_in_world(db, receiver.id, world_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Players do not share a world",
        )
    if social_privacy.interaction_blocked(db, sender.id, receiver.id, world_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Social interaction blocked",
        )

    receiver_status = (
        db.query(models.PremiumStatus)
        .filter(models.PremiumStatus.user_id == receiver.id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    inbox_limit = premium_service.get_message_limit(receiver_status)
    inbox_query = db.query(models.Message).filter(
        models.Message.receiver_id == receiver.id,
        models.Message.world_id == world_id,
    )
    inbox_count = inbox_query.count()
    if inbox_count >= inbox_limit:
        excess_count = inbox_count - inbox_limit + 1
        oldest_messages = (
            inbox_query.order_by(
                models.Message.timestamp.asc(),
                models.Message.id.asc(),
            )
            .with_for_update()
            .limit(excess_count)
            .all()
        )
        for oldest_message in oldest_messages:
            db.delete(oldest_message)

    message = models.Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        world_id=world_id,
        subject=subject,
        content=content,
    )
    db.add(message)

    notification = models.Notification(
        user_id=receiver.id,
        title="Nuevo mensaje privado",
        body=f"Has recibido un mensaje de {sender.username}: {subject}",
        type="message_received",
    )
    db.add(notification)
    try:
        db.flush()
        response = schemas.MessageRead.model_validate(message)
        notification_payload = {
            "id": notification.id,
            "title": notification.title,
            "body": notification.body,
            "type": notification.type,
            "created_at": notification.created_at.isoformat(),
            "read": notification.read,
        }
        db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                socket_manager.notify_user(receiver.id, "notification", notification_payload)
            )
        except RuntimeError:
            asyncio.run(
                socket_manager.notify_user(receiver.id, "notification", notification_payload)
            )
    except Exception:
        pass

    return response


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
        try:
            world_lifecycle.require_world_open(db, world_id, lock=True)
        except ValueError:
            return message
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

    try:
        world_lifecycle.require_world_open(db, world_id, lock=True)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="World is not open") from exc

    db.delete(message)
    db.commit()
    return {"detail": "Message deleted"}
