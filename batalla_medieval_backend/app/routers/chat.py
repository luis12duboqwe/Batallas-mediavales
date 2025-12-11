from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services.chat_manager import chat_manager

router = APIRouter(prefix="/chat", tags=["chat"])

ALLOWED_CHANNELS = {"global", "alliance", "world", "private"}


def _get_alliance_id(db: Session, user_id: int) -> Optional[int]:
    membership = db.query(models.AllianceMember).filter(models.AllianceMember.user_id == user_id).first()
    return membership.alliance_id if membership else None


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

    world_id = current_user.world_id
    alliance_id = _get_alliance_id(db, current_user.id)
    receiver_id: Optional[int] = None

    if channel == "alliance":
        if not alliance_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    if channel == "world":
        if not world_id:
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
        exists = db.query(models.User.id).filter(models.User.id == receiver_id).first()
        if not exists:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    chat_manager.register_connection(
        websocket,
        channel=channel,
        user_id=current_user.id,
        world_id=world_id,
        alliance_id=alliance_id,
        receiver_id=receiver_id,
    )

    try:
        while True:
            data = await websocket.receive_json()
            content = data.get("content") if isinstance(data, dict) else None
            if not content:
                await websocket.send_json({"error": "Message content required"})
                continue

            if not chat_manager.allow_message(current_user.id):
                await websocket.send_json({"error": "Rate limit exceeded"})
                continue

            filtered_content = chat_manager.filter_content(str(content))

            chat_message = models.ChatMessage(
                user_id=current_user.id,
                world_id=world_id if channel in {"world", "global"} else None,
                alliance_id=alliance_id if channel == "alliance" else None,
                channel=channel,
                receiver_id=receiver_id if channel == "private" else None,
                content=filtered_content,
                timestamp=datetime.utcnow(),
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
                world_id=chat_message.world_id,
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

    limit = max(1, min(limit, 100))

    query = db.query(models.ChatMessage).filter(models.ChatMessage.channel == channel)

    if channel == "world":
        if not current_user.world_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="World not set")
        query = query.filter(models.ChatMessage.world_id == current_user.world_id)
    elif channel == "alliance":
        alliance_id = _get_alliance_id(db, current_user.id)
        if not alliance_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not in an alliance")
        query = query.filter(models.ChatMessage.alliance_id == alliance_id)
    elif channel == "private":
        if not user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id required")
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
    limit = max(1, min(limit, 100))
    query = db.query(models.ChatMessage).filter(models.ChatMessage.channel == "private")
    query = query.filter(
        ((models.ChatMessage.user_id == current_user.id) & (models.ChatMessage.receiver_id == user_id))
        | ((models.ChatMessage.user_id == user_id) & (models.ChatMessage.receiver_id == current_user.id))
    )
    messages = query.order_by(models.ChatMessage.timestamp.desc()).limit(limit).all()
    return list(reversed(messages))
