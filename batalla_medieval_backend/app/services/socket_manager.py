import logging
from typing import Optional

import jwt
import socketio

from .. import models
from ..config import get_settings
from ..database import SessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()


class SocketAuthenticationError(ValueError):
    """Raised when a Socket.IO client cannot be mapped to an authenticated user."""


def authenticate_socket_token(token: Optional[str]) -> int:
    """Return a user's id only for a current, verified access token."""
    if not token:
        raise SocketAuthenticationError("missing token")

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.exceptions.InvalidTokenError as exc:
        raise SocketAuthenticationError("invalid token") from exc

    username = payload.get("sub")
    if payload.get("type") != "access":
        raise SocketAuthenticationError("invalid token purpose")
    if not isinstance(username, str) or not username:
        raise SocketAuthenticationError("token subject missing")

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user is None:
            raise SocketAuthenticationError("user not found")
        if payload.get("ver") != user.auth_version:
            raise SocketAuthenticationError("stale token")
        if not user.is_verified:
            raise SocketAuthenticationError("email not verified")
        if user.is_frozen:
            raise SocketAuthenticationError("account frozen")
        return user.id
    finally:
        db.close()


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins,
)


@sio.event
async def connect(sid, environ, auth):
    token = auth.get("token") if isinstance(auth, dict) else None

    try:
        user_id = authenticate_socket_token(token)
    except SocketAuthenticationError as exc:
        logger.warning("Rejected Socket.IO connection %s: %s", sid, exc)
        raise socketio.exceptions.ConnectionRefusedError("authentication failed") from exc

    room = f"user_{user_id}"
    await sio.save_session(sid, {"user_id": user_id})
    await sio.enter_room(sid, room)
    await sio.emit("joined", {"room": room}, to=sid)
    logger.info("Socket connected: sid=%s user_id=%s room=%s", sid, user_id, room)
    return True


@sio.event
async def disconnect(sid):
    logger.info("Socket disconnected: %s", sid)


async def notify_user(user_id: int, event: str, data: dict):
    """Send a notification to a specific authenticated user room."""
    room = f"user_{user_id}"
    try:
        await sio.emit(event, data, room=room)
    except Exception:
        logger.exception("Error sending notification to %s", room)


async def broadcast(event: str, data: dict):
    """Broadcast to all connected users."""
    await sio.emit(event, data)
