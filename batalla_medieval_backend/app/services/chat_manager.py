from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, DefaultDict, Dict, Iterable, Optional, Set, Tuple

from fastapi import WebSocket


class ChatManager:
    def __init__(self) -> None:
        self.global_connections: Set[WebSocket] = set()
        self.world_connections: DefaultDict[int, Set[WebSocket]] = defaultdict(set)
        self.alliance_connections: DefaultDict[int, Set[WebSocket]] = defaultdict(set)
        self.private_connections: DefaultDict[Tuple[int, int], Set[WebSocket]] = defaultdict(set)
        self.connection_meta: Dict[WebSocket, Dict[str, Any]] = {}
        self.last_message_at: Dict[int, datetime] = {}
        self.bad_words = {"badword", "curse", "offensive"}

    @staticmethod
    def _private_key(user_a: int, user_b: int) -> Tuple[int, int]:
        return tuple(sorted((user_a, user_b)))

    def register_connection(
        self,
        websocket: WebSocket,
        *,
        channel: str,
        user_id: int,
        world_id: Optional[int] = None,
        alliance_id: Optional[int] = None,
        receiver_id: Optional[int] = None,
    ) -> None:
        if channel == "global":
            self.global_connections.add(websocket)
        elif channel == "world" and world_id is not None:
            self.world_connections[world_id].add(websocket)
        elif channel == "alliance" and alliance_id is not None:
            self.alliance_connections[alliance_id].add(websocket)
        elif channel == "private" and receiver_id is not None:
            key = self._private_key(user_id, receiver_id)
            self.private_connections[key].add(websocket)
        self.connection_meta[websocket] = {
            "channel": channel,
            "user_id": user_id,
            "world_id": world_id,
            "alliance_id": alliance_id,
            "receiver_id": receiver_id,
        }

    def disconnect(self, websocket: WebSocket) -> None:
        meta = self.connection_meta.pop(websocket, None)
        if not meta:
            return

        channel = meta.get("channel")
        if channel == "global":
            self.global_connections.discard(websocket)
        elif channel == "world" and meta.get("world_id") is not None:
            self.world_connections[meta["world_id"]].discard(websocket)
        elif channel == "alliance" and meta.get("alliance_id") is not None:
            self.alliance_connections[meta["alliance_id"]].discard(websocket)
        elif channel == "private" and meta.get("receiver_id") is not None:
            key = self._private_key(meta["user_id"], meta["receiver_id"])
            self.private_connections[key].discard(websocket)

    def allow_message(self, user_id: int) -> bool:
        now = datetime.utcnow()
        last_sent = self.last_message_at.get(user_id)
        if last_sent and now - last_sent < timedelta(seconds=1):
            return False
        self.last_message_at[user_id] = now
        return True

    def filter_content(self, message: str) -> str:
        filtered = message
        for word in self.bad_words:
            filtered = filtered.replace(word, "***") if filtered else filtered
            filtered = filtered.replace(word.capitalize(), "***") if filtered else filtered
        return filtered

    async def broadcast(
        self,
        *,
        channel: str,
        message: Dict[str, Any],
        sender_id: int,
        world_id: Optional[int] = None,
        alliance_id: Optional[int] = None,
        receiver_id: Optional[int] = None,
    ) -> None:
        connections: Iterable[WebSocket]
        if channel == "global":
            connections = list(self.global_connections)
        elif channel == "world" and world_id is not None:
            connections = list(self.world_connections.get(world_id, set()))
        elif channel == "alliance" and alliance_id is not None:
            connections = list(self.alliance_connections.get(alliance_id, set()))
        elif channel == "private" and receiver_id is not None:
            key = self._private_key(sender_id, receiver_id)
            connections = list(self.private_connections.get(key, set()))
        else:
            connections = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


chat_manager = ChatManager()
