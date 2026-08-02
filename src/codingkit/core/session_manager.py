"""Session manager — CRUD for agent sessions (PLAN T4.3).

The ``SessionManager`` wraps the low-level ``SessionStore`` with
agent-loop-aware logic:

* Save/restore ``AgentLoop`` state (task, history, turns, feedback context).
* Auto-save on interruption.
* Resume rebuilds ``AgentLoop`` context from saved data.
* List / show / delete sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from codingkit.core.agent_loop import AgentLoop, LoopResult, TurnRecord
from codingkit.memory.session_store import SessionStore

__all__ = [
    "SessionManager",
    "SessionInfo",
]


# ---------------------------------------------------------------------------
# SessionInfo
# ---------------------------------------------------------------------------


@dataclass
class SessionInfo:
    """Human-readable summary of a session."""

    __test__ = False

    session_id: str
    created_at: str = ""
    updated_at: str = ""
    status: str = "unknown"
    task_description: str = ""
    total_turns: int = 0
    total_tool_calls: int = 0
    summary: str = ""


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """High-level session CRUD, wrapping ``SessionStore``.

    Usage::

        mgr = SessionManager()
        # Save a loop's state
        mgr.save_loop(loop, result)
        # List all sessions
        for info in mgr.list_sessions():
            print(info.session_id, info.status)
        # Load a session for resume
        loop = mgr.restore_loop(session_id, llm_client)
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the session manager.

        Args:
            storage_dir: Directory for session JSON files.
                Defaults to ``~/.codingkit/sessions/``.
        """
        self._store = SessionStore(storage_dir=storage_dir)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save_loop(
        self,
        loop: AgentLoop,
        result: Optional[LoopResult] = None,
    ) -> str:
        """Save the current state of an ``AgentLoop`` to persistent storage.

        Args:
            loop: The agent loop to save.
            result: Optional ``LoopResult`` to include.

        Returns:
            The session ID of the saved session.
        """
        session_id = loop.session_id
        now = datetime.now(timezone.utc).isoformat()

        # Check if this session already exists
        existing = self._store.load(session_id)

        data: Dict[str, Any] = {
            "session_id": session_id,
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
            "status": loop.state.value,
            "task_description": loop.task,
            "total_turns": loop.current_turn,
            "total_tool_calls": (
                result.total_tool_calls if result else sum(len(t.tool_results) for t in loop.turns)
            ),
            "summary": result.summary if result else "",
            "turns": [_turn_to_dict(t) for t in loop.turns],
            "history": loop._history if hasattr(loop, "_history") else [],
            "feedback_ctx": None,  # would need serialization of FeedbackContext
            "correction_ctx": None,  # would need serialization of CorrectionContext
        }

        self._store.save(session_id, data)
        return session_id

    def restore_loop(
        self,
        session_id: str,
        loop: AgentLoop,
    ) -> bool:
        """Restore an ``AgentLoop`` state from a saved session.

        Args:
            session_id: The session to restore.
            loop: The agent loop instance to populate (must be pre-created).

        Returns:
            ``True`` if the session was restored, ``False`` if not found.
        """
        data = self._store.load(session_id)
        if data is None:
            return False

        # Restore the loop's state
        loop.resume(
            task=data.get("task_description", ""),
            history=data.get("history", []),
            turns=[_turn_from_dict(t) for t in data.get("turns", [])],
        )
        return True

    def list_sessions(self) -> List[SessionInfo]:
        """List all persisted sessions as ``SessionInfo`` objects."""
        sessions = self._store.list_sessions()
        return [_session_to_info(s) for s in sessions]

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get a single session's info by ID.

        Returns:
            ``SessionInfo`` or ``None`` if not found.
        """
        data = self._store.load(session_id)
        if data is None:
            return None
        return _session_to_info(data)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: The session to delete.

        Returns:
            ``True`` if deleted, ``False`` if not found.
        """
        exists = self._store.load(session_id) is not None
        if not exists:
            return False
        self._store.delete(session_id)
        return True

    def get_raw_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the raw session data dict (for ``codingkit session show``)."""
        return self._store.load(session_id)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def save_on_interrupt(self, loop: AgentLoop) -> str:
        """Save the loop state when interrupted (e.g., by ``cancel()``).

        Args:
            loop: The agent loop to save.

        Returns:
            The session ID.
        """
        return self.save_loop(loop)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _turn_to_dict(turn: TurnRecord) -> Dict[str, Any]:
    """Convert a ``TurnRecord`` to a JSON-serializable dict."""
    return {
        "turn_number": turn.turn_number,
        "llm_request": turn.llm_request,
        "llm_response": (
            {
                "content": turn.llm_response.content,
                "tool_calls": [
                    {"name": tc.name, "arguments": tc.arguments, "id": tc.id}
                    for tc in (turn.llm_response.tool_calls or [])
                ],
                "model": turn.llm_response.model,
                "usage": turn.llm_response.usage,
            }
            if turn.llm_response
            else None
        ),
        "parsed_response": (
            {
                "text": turn.parsed_response.text,
                "tool_calls": [
                    {"name": tc.name, "arguments": tc.arguments, "id": tc.id}
                    for tc in (turn.parsed_response.tool_calls or [])
                ],
                "is_complete": turn.parsed_response.is_complete,
                "error": turn.parsed_response.error,
            }
            if turn.parsed_response
            else None
        ),
        "tool_results": [
            {
                "success": tr.success,
                "output": tr.output[:1000],  # truncate long output
                "error": tr.error,
            }
            for tr in turn.tool_results
        ],
        "guardrail_result": (
            {
                "is_dangerous": turn.guardrail_result.is_dangerous,
                "risk_reason": turn.guardrail_result.risk_reason,
            }
            if turn.guardrail_result
            else None
        ),
        "approval_decision": turn.approval_decision.value if turn.approval_decision else None,
        "timestamp": turn.timestamp.isoformat(),
    }


def _turn_from_dict(data: Dict[str, Any]) -> TurnRecord:
    """Convert a dict back to a ``TurnRecord`` (best-effort restore)."""
    from codingkit.core.agent_loop import TurnRecord
    from codingkit.core.llm_client import LLMResponse, ToolCall
    from codingkit.core.response_parser import ParsedResponse
    from codingkit.governance.approval import ApprovalDecision
    from codingkit.governance.guardrail import GuardrailResult
    from codingkit.tools.base import ToolResult

    turn = TurnRecord(turn_number=data.get("turn_number", 0))

    # Restore LLMResponse
    lr = data.get("llm_response")
    if lr:
        turn.llm_response = LLMResponse(
            content=lr.get("content", ""),
            tool_calls=[
                ToolCall(**tc) for tc in lr.get("tool_calls", [])
            ],
            model=lr.get("model", ""),
            usage=lr.get("usage", {}),
        )

    # Restore ParsedResponse
    pr = data.get("parsed_response")
    if pr:
        turn.parsed_response = ParsedResponse(
            text=pr.get("text", ""),
            tool_calls=[
                ToolCall(**tc) for tc in pr.get("tool_calls", [])
            ],
            is_complete=pr.get("is_complete", False),
            error=pr.get("error", ""),
        )

    # Restore ToolResults
    for tr_data in data.get("tool_results", []):
        turn.tool_results.append(
            ToolResult(
                success=tr_data.get("success", False),
                output=tr_data.get("output", ""),
                error=tr_data.get("error"),
            )
        )

    # Restore GuardrailResult
    gr = data.get("guardrail_result")
    if gr:
        turn.guardrail_result = GuardrailResult(
            is_dangerous=gr.get("is_dangerous", False),
            risk_reason=gr.get("risk_reason", ""),
        )

    # Restore ApprovalDecision
    ad = data.get("approval_decision")
    if ad:
        turn.approval_decision = ApprovalDecision(ad)

    # Restore timestamp
    ts = data.get("timestamp")
    if ts:
        try:
            turn.timestamp = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            pass

    return turn


def _session_to_info(data: Dict[str, Any]) -> SessionInfo:
    """Convert a raw session dict to ``SessionInfo``."""
    return SessionInfo(
        session_id=data.get("session_id", "?"),
        created_at=data.get("created_at", "?"),
        updated_at=data.get("updated_at", "?"),
        status=data.get("status", "?"),
        task_description=data.get("task_description", "")[:80],
        total_turns=data.get("total_turns", 0),
        total_tool_calls=data.get("total_tool_calls", 0),
        summary=data.get("summary", "")[:200],
    )