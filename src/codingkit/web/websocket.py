"""WebSocket connection manager for real-time UI updates (PLAN T5.1).

Maintains a pool of WebSocket connections and broadcasts events
(turn completion, state changes, approval requests) to all connected
frontends.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events.

    Usage::

        mgr = ConnectionManager()
        # In a WebSocket endpoint:
        await mgr.connect(websocket)
        # Broadcast to all:
        await mgr.broadcast({"type": "state_change", "data": {...}})
        # On disconnect:
        mgr.disconnect(websocket)
    """

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and add it to the pool."""
        await websocket.accept()
        self._connections.add(websocket)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the pool."""
        self._connections.discard(websocket)
        logger.info("WebSocket client disconnected (%d remaining)", len(self._connections))

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Send a JSON message to all connected clients.

        Silently drops disconnected clients during iteration.
        """
        payload = json.dumps(message, default=str)
        stale: List[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._connections.discard(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# ---------------------------------------------------------------------------
# Event builders
# ---------------------------------------------------------------------------


def state_change_event(
    state: str,
    session_id: str = "",
    task: str = "",
    current_turn: int = 0,
) -> Dict[str, Any]:
    """Build a state-change event for the WebSocket."""
    return {
        "type": "state_change",
        "data": {
            "state": state,
            "session_id": session_id,
            "task": task,
            "current_turn": current_turn,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def turn_complete_event(turn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build a turn-complete event for the WebSocket."""
    return {
        "type": "turn_complete",
        "data": turn_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def approval_request_event(action: Dict[str, Any]) -> Dict[str, Any]:
    """Build an approval-request event for the WebSocket."""
    return {
        "type": "approval_request",
        "data": {
            "action": action,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def log_event(message: str, level: str = "info") -> Dict[str, Any]:
    """Build a log event for the WebSocket."""
    return {
        "type": "log",
        "data": {
            "message": message,
            "level": level,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def error_event(detail: str) -> Dict[str, Any]:
    """Build an error event for the WebSocket."""
    return {
        "type": "error",
        "data": {"detail": detail},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }