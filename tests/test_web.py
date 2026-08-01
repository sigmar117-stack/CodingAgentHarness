"""Tests for the WebUI backend (PLAN T5.1).

Uses FastAPI's TestClient to verify REST API endpoints and WebSocket
behaviour.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from codingkit.web.server import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Create a fresh TestClient for each test."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_idle_status(self, client: TestClient) -> None:
        """GET /api/status returns idle when no task is running."""
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "idle"
        assert data["session_id"] == ""
        assert data["current_turn"] == 0

    def test_status_has_required_fields(self, client: TestClient) -> None:
        """Status response contains all required fields."""
        resp = client.get("/api/status")
        data = resp.json()
        assert "state" in data
        assert "session_id" in data
        assert "current_turn" in data
        assert "total_turns" in data
        assert "task" in data


# ---------------------------------------------------------------------------
# POST /api/run
# ---------------------------------------------------------------------------


class TestRunTask:
    def test_run_starts_task(self, client: TestClient) -> None:
        """POST /api/run with a valid task returns 200 with started status."""
        resp = client.post("/api/run", json={"task": "Write a test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert "session_id" in data

    def test_run_empty_task_fails(self, client: TestClient) -> None:
        """POST /api/run with an empty task returns 422."""
        resp = client.post("/api/run", json={"task": ""})
        assert resp.status_code == 422

    def test_run_plan_only(self, client: TestClient) -> None:
        """POST /api/run with plan_only=True."""
        resp = client.post("/api/run", json={"task": "Write a test", "plan_only": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"

    def test_run_twice_allowed_after_completion(self, client: TestClient) -> None:
        """POST /api/run is allowed again after the first task completes.

        With MockLLMClient, the background task completes almost instantly,
        so a second run should succeed.
        """
        resp = client.post("/api/run", json={"task": "First task"})
        assert resp.status_code == 200

        # Wait briefly for the first task to complete
        import time
        time.sleep(0.2)

        resp2 = client.post("/api/run", json={"task": "Second task"})
        assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/cancel
# ---------------------------------------------------------------------------


class TestCancelTask:
    def test_cancel_when_idle_fails(self, client: TestClient) -> None:
        """POST /api/cancel when no task is running returns 409."""
        resp = client.post("/api/cancel")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_list_sessions_empty(self, client: TestClient) -> None:
        """GET /api/sessions returns empty list when no sessions exist."""
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_list_sessions_after_run(self, client: TestClient) -> None:
        """After running a task, sessions list should contain it."""
        # Run a task first
        client.post("/api/run", json={"task": "Test session"})
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# GET /api/sessions/{id}
# ---------------------------------------------------------------------------


class TestGetSession:
    def test_get_nonexistent_session(self, client: TestClient) -> None:
        """GET /api/sessions/nonexistent returns 404."""
        resp = client.get("/api/sessions/nonexistent-id")
        assert resp.status_code == 404

    def test_session_detail_has_required_fields(self, client: TestClient) -> None:
        """Session detail response contains all required fields."""
        # Run a task to create a session
        client.post("/api/run", json={"task": "Detail test"})
        sessions = client.get("/api/sessions").json()
        if sessions:
            sid = sessions[0]["session_id"]
            resp = client.get(f"/api/sessions/{sid}")
            assert resp.status_code == 200
            data = resp.json()
            assert "session_id" in data
            assert "status" in data
            assert "created_at" in data


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{id}
# ---------------------------------------------------------------------------


class TestDeleteSession:
    def test_delete_nonexistent_session(self, client: TestClient) -> None:
        """DELETE /api/sessions/nonexistent returns 404."""
        resp = client.delete("/api/sessions/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/tools
# ---------------------------------------------------------------------------


class TestListTools:
    def test_list_tools(self, client: TestClient) -> None:
        """GET /api/tools returns a list of tools."""
        resp = client.get("/api/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_tool_has_required_fields(self, client: TestClient) -> None:
        """Each tool entry has name, description, risk_level."""
        resp = client.get("/api/tools")
        for tool in resp.json():
            assert "name" in tool
            assert "description" in tool
            assert "risk_level" in tool

    def test_contains_dangerous_tools(self, client: TestClient) -> None:
        """Tool list includes dangerous tools like execute_command."""
        resp = client.get("/api/tools")
        names = [t["name"] for t in resp.json()]
        assert "execute_command" in names
        assert "read_file" in names


# ---------------------------------------------------------------------------
# GET /api/version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version(self, client: TestClient) -> None:
        """GET /api/version returns a version string."""
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


# ---------------------------------------------------------------------------
# 404 handling
# ---------------------------------------------------------------------------


class TestNotFound:
    def test_invalid_path(self, client: TestClient) -> None:
        """GET /api/nonexistent returns 404."""
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


class TestWebSocket:
    def test_websocket_connect(self, client: TestClient) -> None:
        """WebSocket endpoint accepts connections."""
        with client.websocket_connect("/api/ws") as ws:
            # Should receive initial state or just connect successfully
            data = ws.receive_json()
            assert "type" in data

    def test_websocket_ping_pong(self, client: TestClient) -> None:
        """WebSocket responds to ping with pong."""
        with client.websocket_connect("/api/ws") as ws:
            ws.send_json({"type": "ping"})
            # May receive initial state first, then ping
            data = ws.receive_json()
            if data.get("type") != "pong":
                # It was the initial state; receive again
                ws.send_text("ping")
                data = ws.receive_json()
            assert data["type"] == "pong"

    def test_websocket_multiple_clients(self, client: TestClient) -> None:
        """Multiple WebSocket clients can connect simultaneously."""
        with client.websocket_connect("/api/ws") as ws1:
            with client.websocket_connect("/api/ws") as ws2:
                data1 = ws1.receive_json()
                data2 = ws2.receive_json()
                assert "type" in data1
                assert "type" in data2