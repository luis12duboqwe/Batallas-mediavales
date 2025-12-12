import socketio
import logging

logger = logging.getLogger(__name__)

# Create the Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

@sio.event
async def connect(sid, environ):
    logger.info(f"Socket connected: {sid}")

@sio.event
async def disconnect(sid):
    logger.info(f"Socket disconnected: {sid}")

@sio.on("join")
async def on_join(sid, data):
    """User joins their personal room."""
    user_id = data.get("user_id")
    if user_id:
        room = f"user_{user_id}"
        logger.info(f"User {user_id} joining room {room}")
        sio.enter_room(sid, room)
        await sio.emit("joined", {"room": room}, room=sid)

async def notify_user(user_id: int, event: str, data: dict):
    """Send a notification to a specific user."""
    room = f"user_{user_id}"
    try:
        await sio.emit(event, data, room=room)
    except Exception as e:
        logger.error(f"Error sending notification to {room}: {e}")

async def broadcast(event: str, data: dict):
    """Broadcast to all users."""
    await sio.emit(event, data)
