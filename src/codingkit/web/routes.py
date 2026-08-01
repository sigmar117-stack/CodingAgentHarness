"""REST API routes for the CodingKit WebUI (PLAN T5.1).

Integrates with AgentLoop, SessionManager, ApprovalHandler, and
WebSocket ConnectionManager to provide a real-time web interface.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from codingkit.__version__ import __version__
from codingkit.core.agent_loop import AgentLoop, LoopState, TurnRecord
from codingkit.core.llm_client import MockLLMClient, ToolCall
from codingkit.core.session_manager import SessionManager
from codingkit.governance.approval import ApprovalDecision, ApprovalHandler
from codingkit.tools.registry import default_registry

from .models import (
    ApprovalRequest,
    ErrorResponse,
    RunResponse,
    SessionDetail,
    SessionSummary,
    StatusResponse,
    TaskRequest,
    ToolInfo,
    TurnRecordModel,
)
from .websocket import (
    ConnectionManager,
    approval_request_event,
    error_event,
    log_event,
    state_change_event,
    turn_complete_event,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state — shared across routes
# ---------------------------------------------------------------------------

#: Global session manager (persists across requests).
session_manager = SessionManager()

#: Global WebSocket connection manager.
ws_manager = ConnectionManager()

#: Current agent loop (None when idle).
_current_loop: Optional[AgentLoop] = None

#: Thread running the current loop (None when idle).
_loop_thread: Optional[threading.Thread] = None

#: Lock for thread-safe access to the loop state.
_loop_lock = threading.Lock()

#: Event for signalling cancellation.
_cancel_event = threading.Event()

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Helper: convert a TurnRecord to a serializable dict
# ---------------------------------------------------------------------------


def _turn_to_dict(turn: TurnRecord) -> Dict[str, Any]:
    """Convert a TurnRecord to a JSON-serializable dict."""
    tool_calls = []
    if turn.parsed_response and turn.parsed_response.tool_calls:
        tool_calls = [
            {"name": tc.name, "arguments": tc.arguments, "id": tc.id or ""}
            for tc in turn.parsed_response.tool_calls
        ]

    tool_results = [
        {
            "success": tr.success,
            "output": tr.output[:2000],
            "error": tr.error,
        }
        for tr in turn.tool_results
    ]

    return {
        "turn_number": turn.turn_number,
        "llm_response": turn.llm_response.content if turn.llm_response else None,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "guardrail_result": (
            {
                "is_dangerous": turn.guardrail_result.is_dangerous,
                "risk_reason": turn.guardrail_result.risk_reason,
            }
            if turn.guardrail_result
            else None
        ),
        "approval_decision": turn.approval_decision.value if turn.approval_decision else None,
        "has_test_result": turn.test_result is not None,
        "classification": (
            turn.classification[0].category.value if turn.classification else None
        ),
        "timestamp": turn.timestamp.isoformat() if turn.timestamp else None,
    }


# ---------------------------------------------------------------------------
# Approval callback — pushes to WebSocket
# ---------------------------------------------------------------------------


def _on_approval_request(action: ToolCall) -> None:
    """Called by ApprovalHandler when a dangerous action needs approval.

    Pushes the request to all connected WebSocket clients.
    """
    import asyncio

    action_dict = {
        "name": action.name,
        "arguments": action.arguments,
        "id": action.id or "",
    }
    event = approval_request_event(action_dict)
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(ws_manager.broadcast(event))
        loop.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Turn-complete callback
# ---------------------------------------------------------------------------


def _on_turn_complete(turn: TurnRecord) -> None:
    """Called by AgentLoop after each turn completes.

    Broadcasts the turn data to connected WebSocket clients.
    """
    import asyncio

    event = turn_complete_event(_turn_to_dict(turn))
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(ws_manager.broadcast(event))
        loop.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------


def _run_loop_in_background(task: str, plan_only: bool) -> None:
    """Run the agent loop in a background thread.

    Constructs the loop with a MockLLMClient (or real LLM when configured),
    runs it, and saves the result.
    """
    global _current_loop

    try:
        # Build the loop with WebSocket-aware callbacks
        llm = MockLLMClient(model="mock")
        registry = default_registry()
        approval = ApprovalHandler()
        approval.set_remote_handler(_on_approval_request)

        loop = AgentLoop(
            llm_client=llm,
            tool_registry=registry,
            approval_handler=approval,
            on_turn_complete=_on_turn_complete,
        )

        with _loop_lock:
            _current_loop = loop

        # Broadcast initial state
        _broadcast_state(loop)

        # Run the loop (blocking — this is the background thread)
        result = loop.run(task)

        # Save the session
        session_manager.save_loop(loop, result)

        # Broadcast completion
        with _loop_lock:
            pass  # state is already set by loop.run()

        _broadcast_state(loop)

    except Exception as exc:
        logger.error("Background loop failed: %s", exc)
        _broadcast_error(str(exc))
    finally:
        with _loop_lock:
            if _current_loop and _current_loop.state in (
                LoopState.COMPLETED,
                LoopState.CANCELLED,
                LoopState.ERROR,
            ):
                pass  # Terminal state — keep for status queries
            _cancel_event.clear()


def _broadcast_state(loop: Optional[AgentLoop] = None) -> None:
    """Broadcast the current state via WebSocket."""
    import asyncio

    with _loop_lock:
        l = loop or _current_loop
        if l is None:
            return
        event = state_change_event(
            state=l.state.value,
            session_id=l.session_id,
            task=l.task,
            current_turn=l.current_turn,
        )
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(ws_manager.broadcast(event))
        loop.close()
    except Exception:
        pass


def _broadcast_error(detail: str) -> None:
    """Broadcast an error via WebSocket."""
    import asyncio

    event = error_event(detail)
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(ws_manager.broadcast(event))
        loop.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Return the current agent loop status."""
    with _loop_lock:
        if _current_loop is None:
            return StatusResponse(state="idle", task="")
        return StatusResponse(
            state=_current_loop.state.value,
            session_id=_current_loop.session_id,
            current_turn=_current_loop.current_turn,
            total_turns=len(_current_loop.turns),
            task=_current_loop.task,
        )


@router.post("/run", response_model=RunResponse)
async def run_task(req: TaskRequest) -> RunResponse:
    """Start a new agent task in the background."""
    global _loop_thread

    with _loop_lock:
        if _current_loop is not None and _current_loop.state == LoopState.RUNNING:
            raise HTTPException(
                status_code=409,
                detail="A task is already running. Cancel it first.",
            )

    # Start the background thread
    thread = threading.Thread(
        target=_run_loop_in_background,
        args=(req.task, req.plan_only),
        daemon=True,
    )
    thread.start()
    _loop_thread = thread

    # Get the session ID from the loop (may not be set yet)
    with _loop_lock:
        sid = _current_loop.session_id if _current_loop else ""

    return RunResponse(
        session_id=sid,
        status="started",
        message="Task started in background.",
    )


@router.post("/cancel")
async def cancel_task() -> Dict[str, Any]:
    """Cancel the currently running task."""
    with _loop_lock:
        if _current_loop is None or _current_loop.state != LoopState.RUNNING:
            raise HTTPException(
                status_code=409,
                detail="No running task to cancel.",
            )
        _cancel_event.set()
        _current_loop.cancel()
        session_manager.save_on_interrupt(_current_loop)

    # Broadcast cancellation
    _broadcast_state()

    return {"status": "cancelled", "message": "Task cancelled."}


@router.get("/sessions", response_model=List[SessionSummary])
async def list_sessions() -> List[SessionSummary]:
    """List all saved sessions."""
    sessions = session_manager.list_sessions()
    return [
        SessionSummary(
            session_id=s.session_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
            status=s.status,
            task_description=s.task_description,
            total_turns=s.total_turns,
            total_tool_calls=s.total_tool_calls,
            summary=s.summary,
        )
        for s in sessions
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetail,
    responses={404: {"model": ErrorResponse}},
)
async def get_session(session_id: str) -> SessionDetail:
    """Get details for a specific session."""
    info = session_manager.get_session(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    raw = session_manager.get_raw_data(session_id)
    turns = []
    if raw and "turns" in raw:
        turns = [TurnRecordModel(**_turn_dict_to_model(t)) for t in raw["turns"]]

    return SessionDetail(
        session_id=info.session_id,
        created_at=info.created_at,
        updated_at=info.updated_at,
        status=info.status,
        task_description=info.task_description,
        total_turns=info.total_turns,
        total_tool_calls=info.total_tool_calls,
        summary=info.summary,
        turns=turns,
    )


def _turn_dict_to_model(t: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a raw turn dict to a TurnRecordModel-compatible dict."""
    return {
        "turn_number": t.get("turn_number", 0),
        "llm_response": (
            t.get("llm_response", {}).get("content", "")
            if isinstance(t.get("llm_response"), dict)
            else None
        ),
        "tool_calls": [
            {"name": tc.get("name", ""), "arguments": tc.get("arguments", {}), "id": tc.get("id", "")}
            for tc in (
                t.get("parsed_response", {}).get("tool_calls", [])
                if isinstance(t.get("parsed_response"), dict)
                else []
            )
        ],
        "tool_results": t.get("tool_results", []),
        "guardrail_result": t.get("guardrail_result"),
        "approval_decision": t.get("approval_decision"),
        "has_test_result": t.get("has_test_result", False),
        "classification": t.get("classification"),
        "timestamp": t.get("timestamp"),
    }


@router.delete(
    "/sessions/{session_id}",
    responses={404: {"model": ErrorResponse}},
)
async def delete_session(session_id: str) -> Dict[str, Any]:
    """Delete a session."""
    deleted = session_manager.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {"status": "deleted", "message": f"Session '{session_id}' deleted."}


@router.post("/approve")
async def approve_action(req: ApprovalRequest) -> Dict[str, Any]:
    """Submit an approval decision for a dangerous action."""
    with _loop_lock:
        if _current_loop is None:
            raise HTTPException(status_code=409, detail="No active session.")
        if req.session_id != _current_loop.session_id:
            raise HTTPException(
                status_code=409,
                detail=f"Session mismatch: '{req.session_id}' != '{_current_loop.session_id}'.",
            )

        approval = _current_loop._approval  # Access the handler

    decision_map = {
        "approved": ApprovalDecision.APPROVED,
        "rejected": ApprovalDecision.REJECTED,
        "modified": ApprovalDecision.MODIFIED,
    }
    decision = decision_map.get(req.decision)
    if decision is None:
        raise HTTPException(status_code=400, detail=f"Invalid decision: '{req.decision}'.")

    approval.set_remote_decision(decision, req.modified_params)

    return {"status": "ok", "decision": req.decision}


@router.get("/tools", response_model=List[ToolInfo])
async def list_tools() -> List[ToolInfo]:
    """List all available tools."""
    registry = default_registry()
    return [
        ToolInfo(
            name=t.name,
            description=t.description,
            risk_level=t.risk_level.value,
            parameters=t.parameters if hasattr(t, "parameters") else {},
        )
        for t in registry.list_all()
    ]


@router.get("/version")
async def get_version() -> Dict[str, str]:
    """Return the CodingKit version."""
    return {"version": __version__}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time status updates.

    On connect, sends the current state.  Then streams events until
    disconnect.
    """
    await ws_manager.connect(websocket)

    try:
        # Send initial state
        with _loop_lock:
            if _current_loop is not None:
                init = state_change_event(
                    state=_current_loop.state.value,
                    session_id=_current_loop.session_id,
                    task=_current_loop.task,
                    current_turn=_current_loop.current_turn,
                )
                await websocket.send_json(init)

        # Keep connection alive — read (and discard) any messages from client
        while True:
            try:
                data = await websocket.receive_text()
                # Client can send ping messages; respond with pong
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        ws_manager.disconnect(websocket)