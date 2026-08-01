"""Tests for session management (PLAN T4.3).

Verification targets:
  ① Create session → file exists
  ② List sessions → includes created session
  ③ Delete session → file does not exist
  ④ Save and restore AgentLoop context
  ⑤ Save on interrupt
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codingkit.core.agent_loop import AgentLoop, LoopState, TurnRecord
from codingkit.core.llm_client import LLMResponse, MockLLMClient
from codingkit.core.session_manager import (
    SessionInfo,
    SessionManager,
    _session_to_info,
    _turn_from_dict,
    _turn_to_dict,
)
from codingkit.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_store(tmp_path: Path) -> SessionManager:
    return SessionManager(storage_dir=tmp_path / "sessions")


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient(model="mock")


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


# ---------------------------------------------------------------------------
# ① Create session → file exists
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_save_loop_creates_file(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("test task")
        session_id = tmp_store.save_loop(loop)
        assert session_id == loop.session_id
        # Verify the file exists
        data = tmp_store.get_raw_data(session_id)
        assert data is not None
        assert data["session_id"] == session_id

    def test_save_loop_with_result(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        result = loop.run("test")
        session_id = tmp_store.save_loop(loop, result)
        data = tmp_store.get_raw_data(session_id)
        assert data is not None
        assert data["status"] == "completed"
        assert data["task_description"] == "test"

    def test_save_includes_turns(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("test")
        tmp_store.save_loop(loop)
        data = tmp_store.get_raw_data(loop.session_id)
        assert data is not None
        assert len(data["turns"]) >= 1
        assert data["total_turns"] >= 1


# ---------------------------------------------------------------------------
# ② List sessions → includes created session
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_list_empty(self, tmp_store: SessionManager) -> None:
        sessions = tmp_store.list_sessions()
        assert sessions == []

    def test_list_includes_saved(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("task 1")
        tmp_store.save_loop(loop)
        sessions = tmp_store.list_sessions()
        assert len(sessions) >= 1
        assert any(s.session_id == loop.session_id for s in sessions)

    def test_list_multiple_sessions(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        for task in ["task A", "task B", "task C"]:
            loop = AgentLoop(llm_client=mock_llm, max_turns=3)
            mock_llm._responses = [LLMResponse(content="Done", model="mock")]
            loop.run(task)
            tmp_store.save_loop(loop)
        sessions = tmp_store.list_sessions()
        assert len(sessions) == 3

    def test_list_returns_session_info(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("test task")
        tmp_store.save_loop(loop)
        sessions = tmp_store.list_sessions()
        assert all(isinstance(s, SessionInfo) for s in sessions)


# ---------------------------------------------------------------------------
# ③ Delete session → file does not exist
# ---------------------------------------------------------------------------


class TestDeleteSession:
    def test_delete_existing(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("test")
        tmp_store.save_loop(loop)
        assert tmp_store.delete_session(loop.session_id) is True
        assert tmp_store.get_raw_data(loop.session_id) is None

    def test_delete_nonexistent(self, tmp_store: SessionManager) -> None:
        assert tmp_store.delete_session("nonexistent") is False

    def test_get_session(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("test")
        tmp_store.save_loop(loop)
        info = tmp_store.get_session(loop.session_id)
        assert info is not None
        assert info.session_id == loop.session_id

    def test_get_session_nonexistent(self, tmp_store: SessionManager) -> None:
        assert tmp_store.get_session("nonexistent") is None


# ---------------------------------------------------------------------------
# ④ Save and restore AgentLoop context
# ---------------------------------------------------------------------------


class TestRestore:
    def test_restore_loop(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("test task")
        session_id = tmp_store.save_loop(loop)

        # Create a new loop and restore
        restored = AgentLoop(llm_client=mock_llm, max_turns=3)
        success = tmp_store.restore_loop(session_id, restored)
        assert success is True
        assert restored.task == "test task"

    def test_restore_nonexistent(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        success = tmp_store.restore_loop("nonexistent", loop)
        assert success is False

    def test_restore_preserves_turns(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("test")
        session_id = tmp_store.save_loop(loop)

        restored = AgentLoop(llm_client=mock_llm, max_turns=3)
        tmp_store.restore_loop(session_id, restored)
        assert len(restored.turns) >= 1


# ---------------------------------------------------------------------------
# ⑤ Save on interrupt
# ---------------------------------------------------------------------------


class TestSaveOnInterrupt:
    def test_save_on_interrupt(self, tmp_store: SessionManager, mock_llm: MockLLMClient) -> None:
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("test")
        session_id = tmp_store.save_on_interrupt(loop)
        data = tmp_store.get_raw_data(session_id)
        assert data is not None
        assert data["status"] in ("completed", "idle")


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_turn_round_trip(self, mock_llm: MockLLMClient) -> None:
        """TurnRecord → dict → TurnRecord preserves key fields."""
        loop = AgentLoop(llm_client=mock_llm, max_turns=3)
        mock_llm._responses = [LLMResponse(content="Test", model="mock")]
        loop.run("test")
        if loop.turns:
            original = loop.turns[0]
            data = _turn_to_dict(original)
            restored = _turn_from_dict(data)
            assert restored.turn_number == original.turn_number
            assert restored.llm_response is not None or original.llm_response is None

    def test_session_info_from_dict(self) -> None:
        data = {
            "session_id": "test-123",
            "created_at": "2026-01-01T00:00:00",
            "status": "completed",
            "task_description": "Write a test",
            "total_turns": 5,
            "total_tool_calls": 3,
            "summary": "All done",
        }
        info = _session_to_info(data)
        assert info.session_id == "test-123"
        assert info.status == "completed"
        assert info.total_turns == 5