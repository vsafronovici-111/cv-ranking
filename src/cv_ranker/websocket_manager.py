from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSConnectionManager:
    """Tracks WebSocket clients subscribed to `conversations/{conversation_id}` topics."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}

    async def connect(self, conversation_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(conversation_id, set()).add(websocket)

    def disconnect(self, conversation_id: int, websocket: WebSocket) -> None:
        connections = self._connections.get(conversation_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            del self._connections[conversation_id]

    async def broadcast(self, conversation_id: int, payload: dict[str, Any]) -> None:
        connections = self._connections.get(conversation_id)
        if not connections:
            return
        for websocket in list(connections):
            try:
                await websocket.send_json(payload)
            except Exception:
                logger.exception("Failed to send message to a websocket client; dropping it")
                self.disconnect(conversation_id, websocket)
