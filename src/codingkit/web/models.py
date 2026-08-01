"""Pydantic models for the WebUI REST API (PLAN T5.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class TaskRequest(BaseModel):
    """Request body for POST /api/run."""

    task: str = Field(..., min_length=1, max_length=10000, description="Task description")
    plan_only: bool = Field(False, description="Only generate a plan, do not execute")


class ApprovalRequest(BaseModel):
    """Request body for POST /api/approve."""

    session_id: str = Field(..., description="Session ID the approval is for")
    decision: str = Field(..., pattern=r"^(approved|rejected|modified)$", description="y/n/m")
    modified_params: Optional[Dict[str, Any]] = Field(None, description="Modified params (only when decision=modified)")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class StatusResponse(BaseModel):
    """Response for GET /api/status."""

    state: str = Field(..., description="Current loop state")
    session_id: str = Field("", description="Active session ID, if any")
    current_turn: int = Field(0, description="Current turn number")
    total_turns: int = Field(0, description="Total turns executed")
    task: str = Field("", description="Current task description")


class ToolInfo(BaseModel):
    """Information about a single tool."""

    name: str
    description: str
    risk_level: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class TurnRecordModel(BaseModel):
    """Serializable turn record for API responses."""

    turn_number: int
    llm_response: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    guardrail_result: Optional[Dict[str, Any]] = None
    approval_decision: Optional[str] = None
    has_test_result: bool = False
    classification: Optional[str] = None
    timestamp: Optional[str] = None


class SessionSummary(BaseModel):
    """Summary of a session for list views."""

    session_id: str
    created_at: str
    updated_at: str
    status: str
    task_description: str = ""
    total_turns: int = 0
    total_tool_calls: int = 0
    summary: str = ""


class SessionDetail(BaseModel):
    """Full session detail."""

    session_id: str
    created_at: str
    updated_at: str
    status: str
    task_description: str = ""
    total_turns: int = 0
    total_tool_calls: int = 0
    summary: str = ""
    turns: List[TurnRecordModel] = Field(default_factory=list)


class RunResponse(BaseModel):
    """Response for POST /api/run."""

    session_id: str
    status: str = "started"
    message: str = ""


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    error_code: Optional[str] = None


# ---------------------------------------------------------------------------
# WebSocket message models
# ---------------------------------------------------------------------------


class WSMessage(BaseModel):
    """Message sent over WebSocket to the frontend."""

    type: str = Field(..., description="Message type: turn_complete | state_change | approval_request | error | log")
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())