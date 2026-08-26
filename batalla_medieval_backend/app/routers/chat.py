from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..schemas import privacy as privacy_schema
from ..services import community as community_service
from ..services import social_privacy
from ..services.chat_manager import chat_manager
from ..utils import utc_now

router = APIRouter(tags=["chat"])

ALLOWED_CHANNELS = {"global", "alliance", "world", "private"}


def _get_active_world_id(db: Session, user: models.User) -> Optional[int]:
    """Return the selected world only when durable membership still exists."""

    if user.world_id is None:
        return None
    membership = (
        db.query(models.PlayerWorld.id)
        .filter(
            models.PlayerWorld.user_id == user.id,
            models.PlayerWorld.world_id == user.world_id,
        )
        .first()
    )
    return user.world_id if membership else None


def _get_alliance_id(db: Session, user_id: int, world_id: int) -> Optional[int]:
    membership = (
        db.query(models.AllianceMember)
        .join(models.Alliance, models.Alliance.id == models.AllianceMember.alliance_id)
        .filter(
            models.AllianceMember.user_id == user_id,
            models.Alliance.world_id == world_id,
        )
        .first()
    )
    return membership.alliance_id if membership else None


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


def _normalize_content(content: object) -> str:
    normalized = str(content or "").strip()
    if not normalized:
        raise ValueError("Message content required")
    if len(normalized) > community_service.MAX_CHAT_MESSAGE_LENGTH:
        raise ValueError(
            f"Message exceeds {community_service.MAX_CHAT_MESSAGE_LENGTH} characters"
        )
    return chat_manager.filter_content(normalized)


@router.websocket("/{channel}")
async def websocket_chat(websocket: WebSocket, channel: str, db: Session = Depends(get_db)):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if channel not in ALLOWED_CHANNELS:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return

    try:
        current_user = await get_current_user(token=token, db=db)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    world_id = _get_active_world_id(db, current_user)
    if world_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    alliance_id = _get_alliance_id(db, current_user.id, world_id)
    receiver_id: Optional[int] = None

    if channel == "alliance" and not alliance_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if channel == "private":
        receiver = websocket.query_params.get("receiver_id")
        if not receiver:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        try:
            receiver_id = int(receiver)
        except ValueError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if receiver_id == current_user.id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if not _user_in_world(db, receiver_id, world_id):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if social_privacy.interaction_blocked(
            db,
            current_user.id,
            receiver_id,
            world_id,
        ):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    try:
        chat_manager.register_connection(
            websocket,
            channel=channel,
            user_id=current_user.id,
            world_id=world_id,
            alliance_id=alliance_id,
            receiver_id=receiver_id,
        )
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        while True:
            data = await websocket.receive_json()
            raw_content = data.get("content") if isinstance(data, dict) else None
            try:
                filtered_content = _normalize_content(raw_content)
            except ValueError as exc:
                await websocket.send_json({"error": str(exc)})
                continue

            # Re-check privacy on every private send so a block takes effect on
            # an already-open socket without waiting for reconnection.
            if channel == "private" and receiver_id is not None:
                if social_privacy.interaction_blocked(
                    db,
                    current_user.id,
                    receiver_id,
                    world_id,
                ):
                    await websocket.send_json({"error": "Private interaction blocked"})
                    continue

            if channel == "alliance":
                current_alliance_id = _get_alliance_id(db, current_user.id, world_id)
                if current_alliance_id != alliance_id:
                    await websocket.send_json({"error": "Alliance membership changed"})
                    continue

            if not chat_manager.allow_message(current_user.id):
                await websocket.send_json({"error": "Rate limit exceeded"})
                continue

            chat_message = models.ChatMessage(
                user_id=current_user.id,
                world_id=world_id,
                alliance_id=alliance_id if channel == "alliance" else None,
                channel=channel,
                receiver_id=receiver_id if channel == "private" else None,
                content=filtered_content,
                timestamp=utc_now(),
            )
            db.add(chat_message)
            db.commit()
            db.refresh(chat_message)

            payload = {
                "id": chat_message.id,
                "user_id": current_user.id,
                "username": current_user.username,
                "world_id": chat_message.world_id,
                "alliance_id": chat_message.alliance_id,
                "channel": chat_message.channel,
                "receiver_id": chat_message.receiver_id,
                "content": chat_message.content,
                "timestamp": chat_message.timestamp.isoformat(),
            }

            await chat_manager.broadcast(
                channel=channel,
                message=payload,
                sender_id=current_user.id,
                world_id=world_id,
                alliance_id=chat_message.alliance_id,
                receiver_id=receiver_id,
            )
    except WebSocketDisconnect:
        chat_manager.disconnect(websocket)


@router.get("/history/{channel}", response_model=list[schemas.ChatMessageRead])
def get_chat_history(
    channel: str,
    limit: int = 50,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if channel not in ALLOWED_CHANNELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid channel")

    world_id = _get_active_world_id(db, current_user)
    if world_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active world not joined")

    limit = max(1, min(limit, 100))
    query = db.query(models.ChatMessage).filter(
        models.ChatMessage.channel == channel,
        models.ChatMessage.world_id == world_id,
    )

    if channel == "alliance":
        alliance_id = _get_alliance_id(db, current_user.id, world_id)
        if not alliance_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not in an alliance")
        query = query.filter(models.ChatMessage.alliance_id == alliance_id)
    elif channel == "private":
        if not user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id required")
        if user_id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot chat with yourself")
        if not _user_in_world(db, user_id, world_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Players do not share active world")
        query = query.filter(
            ((models.ChatMessage.user_id == current_user.id) & (models.ChatMessage.receiver_id == user_id))
            | ((models.ChatMessage.user_id == user_id) & (models.ChatMessage.receiver_id == current_user.id))
        )

    messages = query.order_by(models.ChatMessage.timestamp.desc()).limit(limit).all()
    return list(reversed(messages))


@router.get("/private/{user_id}", response_model=list[schemas.ChatMessageRead])
def private_history(
    user_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    world_id = _get_active_world_id(db, current_user)
    if world_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active world not joined")
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot chat with yourself")
    if not _user_in_world(db, user_id, world_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Players do not share active world")

    limit = max(1, min(limit, 100))
    query = db.query(models.ChatMessage).filter(
        models.ChatMessage.channel == "private",
        models.ChatMessage.world_id == world_id,
        (
            ((models.ChatMessage.user_id == current_user.id) & (models.ChatMessage.receiver_id == user_id))
            | ((models.ChatMessage.user_id == user_id) & (models.ChatMessage.receiver_id == current_user.id))
        ),
    )
    messages = query.order_by(models.ChatMessage.timestamp.desc()).limit(limit).all()
    return list(reversed(messages))


@router.post("/blocks", response_model=privacy_schema.UserBlockRead)
def block_user(
    payload: privacy_schema.UserBlockCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return social_privacy.block_user(
        db,
        current_user.id,
        payload.user_id,
        payload.world_id,
    )


@router.delete("/blocks/{world_id}/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unblock_user(
    world_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    social_privacy.unblock_user(db, current_user.id, user_id, world_id)


@router.get("/blocks/{world_id}", response_model=list[privacy_schema.UserBlockRead])
def list_blocks(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return social_privacy.list_blocks(db, current_user.id, world_id)
