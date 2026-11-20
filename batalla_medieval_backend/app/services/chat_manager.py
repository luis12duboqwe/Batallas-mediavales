from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, DefaultDict, Dict, Iterable, Optional, Set, Tuple

from fastapi import WebSocket

from ..utils import utc_now


class ChatManager:
    def __init__(self) -> None:
        # "global" means global within one game world. Worlds are independent
        # gameplay partitions and must never share chat recipients.
        self.global_connections: DefaultDict[int, Set[WebSocket]] = defaultdict(set)
        self.world_connections: DefaultDict[int, Set[WebSocket]] = defaultdict(set)
        self.alliance_connections: DefaultDict[int, Set[WebSocket]] = defaultdict(set)
        self.private_connections: DefaultDict[Tuple[int, int, int], Set[WebSocket]] = defaultdict(set)
        self.connection_meta: Dict[WebSocket, Dict[str, Any]] = {}
        self.last_message_at: Dict[int, datetime] = {}
        self.bad_words = {"badword", "curse", "offensive"}

    @staticmethod
    def _private_key(world_id: int, user_a: int, user_b: int) -> Tuple[int, int, int]:
        """One private conversation per world, not per account pair globally."""
        first, second = sorted((user_a, user_b))
        return (world_id, first, second)

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
        if channel == "global" and world_id is not None:
            self.global_connections[world_id].add(websocket)
        elif channel == "world" and world_id is not None:
            self.world_connections[world_id].add(websocket)
        elif channel == "alliance" and alliance_id is not None:
            self.alliance_connections[alliance_id].add(websocket)
        elif channel == "private" and receiver_id is not None and world_id is not None:
            key = self._private_key(world_id, user_id, receiver_id)
            self.private_connections[key].add(websocket)
        else:
            raise ValueError("Chat connection is missing required scope metadata")

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
        if channel == "global" and meta.get("world_id") is not None:
            self.global_connections[meta["world_id"]].discard(websocket)
        elif channel == "world" and meta.get("world_id") is not None:
            self.world_connections[meta["world_id"]].discard(websocket)
        elif channel == "alliance" and meta.get("alliance_id") is not None:
            self.alliance_connections[meta["alliance_id"]].discard(websocket)
        elif channel == "private" and meta.get("receiver_id") is not None and meta.get("world_id") is not None:
            key = self._private_key(meta["world_id"], meta["user_id"], meta["receiver_id"])
            self.private_connections[key].discard(websocket)

    def allow_message(self, user_id: int) -> bool:
        now = utc_now()
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
        authorized_user_ids: Set[int] | None = None,
    ) -> None:
        connections: Iterable[WebSocket]
        if channel == "global" and world_id is not None:
            connections = list(self.global_connections.get(world_id, set()))
        elif channel == "world" and world_id is not None:
            connections = list(self.world_connections.get(world_id, set()))
        elif channel == "alliance" and alliance_id is not None:
            # An evicted member may still have an open WebSocket. Fetch a
            # CURRENT membership set per message at the router boundary;
            # an absent authorization snapshot fails closed.
            connections = []
            if authorized_user_ids is not None and world_id is not None:
                for socket in list(self.alliance_connections.get(alliance_id, set())):
                    meta = self.connection_meta.get(socket)
                    if (
                        not meta
                        or meta.get("world_id") != world_id
                        or meta.get("alliance_id") != alliance_id
                        or meta.get("user_id") not in authorized_user_ids
                    ):
                        self.disconnect(socket)
                        continue
                    connections.append(socket)
        elif channel == "private" and receiver_id is not None and world_id is not None:
            key = self._private_key(world_id, sender_id, receiver_id)
            connections = list(self.private_connections.get(key, set()))
        else:
            connections = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


chat_manager = ChatManager()
