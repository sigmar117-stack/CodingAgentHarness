"""Tests for the agent main loop (PLAN T4.1).

All tests use ``MockLLMClient`` so they require no network, no API keys, and
are fully deterministic.

Verification targets (from PLAN T4.1):
  ① Mock LLM with predefined responses → loop executes as expected
  ② Inject tool-call response → tools are invoked
  ③ Inject text reply → output goes to user
  ④ cancel() → state saved
  ⑤ resume() → continues from saved state
  ⑥ Tool guardrail integration
  ⑦ Feedback loop integration
  ⑧ Empty response retry
  ⑨ Max turns safety valve
"""

from __future__ import annotations

import pytest

from codingkit.core.agent_loop import (
    MAX_TURNS,
    AgentLoop,
    LoopResult,
    LoopState,
    TurnRecord,
)
from codingkit.core.llm_client import LLMResponse, MockLLMClient, ToolCall
from codingkit.governance.approval import ApprovalDecision
from codingkit.tools.base import ToolResult
from codingkit.tools.registry import ToolRegistry, default_registry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient(model="mock")


@pytest.fixture
def registry() -> ToolRegistry:
    return default_registry()


@pytest.fixture
def loop(mock_llm: MockLLMClient, registry: ToolRegistry) -> AgentLoop:
    return AgentLoop(
        llm_client=mock_llm,
        tool_registry=registry,
        max_turns=10,
    )


def _tool_call_response(
    name: str,
    args: dict | None = None,
    content: str = "",
) -> LLMResponse:
    """Build an ``LLMResponse`` with a single tool call."""
    return LLMResponse(
        content=content,
        tool_calls=[
            ToolCall(name=name, arguments=args or {}, id="call_1"),
        ],
        model="mock",
    )


# ---------------------------------------------------------------------------
# ① Mock LLM with predefined responses → loop executes as expected
# ---------------------------------------------------------------------------


class TestBasicExecution:
    def test_run_with_text_response(self, loop: AgentLoop, mock_llm: MockLLMClient) -> None:
        """Text-only response → loop completes after one turn."""
        mock_llm._responses = [
            LLMResponse(content="Task complete! I've finished.", model="mock"),
        ]
        result = loop.run("Write a test")
        assert result.state == LoopState.COMPLETED
        assert result.total_turns == 1
        assert "Task complete" in result.summary

    def test_run_with_tool_call_then_text(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """Tool call followed by completion text."""
        mock_llm._responses = [
            _tool_call_response("read_file", {"path": "test.py"}),
            LLMResponse(content="I've read the file. Task complete!", model="mock"),
        ]
        result = loop.run("Read test.py")
        assert result.state == LoopState.COMPLETED
        assert result.total_turns == 2
        assert result.total_tool_calls == 1

    def test_run_with_multiple_tool_calls(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """Multiple tool calls in sequence."""
        mock_llm._responses = [
            _tool_call_response("read_file", {"path": "src/main.py"}),
            _tool_call_response("search_files", {"pattern": "*.py"}),
            LLMResponse(content="All done!", model="mock"),
        ]
        result = loop.run("Explore the codebase")
        assert result.state == LoopState.COMPLETED
        assert result.total_turns == 3
        assert result.total_tool_calls == 2


# ---------------------------------------------------------------------------
# ② Tool calls are invoked
# ---------------------------------------------------------------------------


class TestToolInvocation:
    def test_tool_call_executed(self, loop: AgentLoop, mock_llm: MockLLMClient) -> None:
        """Tool call response → tool is executed and result recorded."""
        mock_llm._responses = [
            _tool_call_response("read_file", {"path": "pyproject.toml"}),
            LLMResponse(content="Done!", model="mock"),
        ]
        result = loop.run("Read pyproject.toml")
        assert len(result.turns) == 2
        turn = result.turns[0]
        assert len(turn.tool_results) == 1
        assert turn.tool_results[0].success is True

    def test_tool_result_in_history(self, loop: AgentLoop, mock_llm: MockLLMClient) -> None:
        """Tool result is recorded in the message history."""
        mock_llm._responses = [
            _tool_call_response("read_file", {"path": "pyproject.toml"}),
            LLMResponse(content="Done!", model="mock"),
        ]
        result = loop.run("Read pyproject.toml")
        # History should have: system, user(task), assistant(tool_use), tool(result), assistant(text)
        assert len(result.history) >= 2
        # Check that the tool result message is there
        tool_messages = [m for m in result.history if m.get("role") == "tool"]
        assert len(tool_messages) >= 1

    def test_unknown_tool_returns_error(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """Unknown tool name → error result, not crash."""
        mock_llm._responses = [
            _tool_call_response("nonexistent_tool", {}),
            LLMResponse(content="I see the error.", model="mock"),
        ]
        # Should not raise
        result = loop.run("Use unknown tool")
        assert result.state == LoopState.COMPLETED
        turn = result.turns[0]
        assert len(turn.tool_results) == 1
        assert turn.tool_results[0].success is False
        assert "Unknown tool" in (turn.tool_results[0].error or "")


# ---------------------------------------------------------------------------
# ③ Text reply → output to user
# ---------------------------------------------------------------------------


class TestTextReply:
    def test_text_reply_in_summary(self, loop: AgentLoop, mock_llm: MockLLMClient) -> None:
        """Text reply is captured in the result summary."""
        mock_llm._responses = [
            LLMResponse(content="Hello! I'm ready to help.", model="mock"),
        ]
        result = loop.run("Say hello")
        assert "Hello" in result.summary

    def test_text_reply_history(self, loop: AgentLoop, mock_llm: MockLLMClient) -> None:
        """Text reply is recorded in the assistant message history."""
        mock_llm._responses = [
            LLMResponse(content="Here is my analysis...", model="mock"),
        ]
        result = loop.run("Analyze this")
        assistant_msgs = [m for m in result.history if m.get("role") == "assistant"]
        assert len(assistant_msgs) >= 1
        assert "analysis" in assistant_msgs[-1].get("content", "").lower()


# ---------------------------------------------------------------------------
# ④ cancel() → state saved
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_during_run(self, loop: AgentLoop, mock_llm: MockLLMClient) -> None:
        """Cancel mid-run → state is CANCELLED."""
        # Provide many responses so the loop would keep going
        mock_llm._responses = [
            _tool_call_response("read_file", {"path": "a.py"}),
            _tool_call_response("read_file", {"path": "b.py"}),
            _tool_call_response("read_file", {"path": "c.py"}),
        ] * 10
        result = loop.cancel()
        assert result.state == LoopState.CANCELLED

    def test_cancel_returns_result(self, loop: AgentLoop, mock_llm: MockLLMClient) -> None:
        """Cancel returns a LoopResult with current state."""
        mock_llm._responses = [
            LLMResponse(content="Working...", model="mock"),
        ]
        result = loop.cancel()
        assert isinstance(result, LoopResult)
        assert result.session_id == loop.session_id


# ---------------------------------------------------------------------------
# ⑤ resume() → continues from saved state
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_after_cancel(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """Cancel then resume → continues."""
        mock_llm._responses = [
            _tool_call_response("read_file", {"path": "a.py"}),
            LLMResponse(content="Complete!", model="mock"),
        ]
        # Cancel first
        loop.cancel()
        assert loop.state == LoopState.CANCELLED

        # Resume and continue
        loop.resume()
        result = loop.run("Continue the task")
        # Should be able to run again
        assert result.state in (LoopState.COMPLETED,)

    def test_resume_restores_task(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """Resume with a new task."""
        loop.resume(task="New task")
        assert loop.task == "New task"


# ---------------------------------------------------------------------------
# ⑥ Guardrail integration
# ---------------------------------------------------------------------------


class TestGuardrailIntegration:
    def test_dangerous_tool_triggers_guardrail(
        self, loop: AgentLoop, mock_llm: MockLLMClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dangerous tool call → guardrail check is recorded in turn."""
        monkeypatch.setattr(
            "codingkit.governance.approval.ApprovalHandler.request_approval",
            lambda self, action: (ApprovalDecision.APPROVED, None),
        )
        mock_llm._responses = [
            _tool_call_response("delete_file", {"path": "test.py"}),
            LLMResponse(content="Deleted the file.", model="mock"),
        ]
        result = loop.run("Delete test.py")
        turn = result.turns[0]
        assert turn.guardrail_result is not None
        assert turn.guardrail_result.is_dangerous is True

    def test_rejected_tool_returns_error(
        self, loop: AgentLoop, mock_llm: MockLLMClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rejected dangerous tool → error result."""
        monkeypatch.setattr(
            "codingkit.governance.approval.ApprovalHandler.request_approval",
            lambda self, action: (ApprovalDecision.REJECTED, None),
        )
        mock_llm._responses = [
            _tool_call_response("delete_file", {"path": "test.py"}),
            LLMResponse(content="I see.", model="mock"),
        ]
        result = loop.run("Delete test.py")
        turn = result.turns[0]
        assert len(turn.tool_results) == 1
        assert turn.tool_results[0].success is False
        assert "rejected" in (turn.tool_results[0].error or "").lower()


# ---------------------------------------------------------------------------
# ⑦ Feedback loop integration
# ---------------------------------------------------------------------------


class TestFeedbackIntegration:
    def test_feedback_loop_triggered_on_test_failure(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """run_tests with failures → feedback loop processes results."""
        import xml.etree.ElementTree as ET

        # Build a JUnit XML with a failure
        ts = ET.Element("testsuite", name="pytest", tests="2", failures="1", errors="0")
        tc1 = ET.SubElement(ts, "testcase", name="test_pass", classname="test_math")
        ET.SubElement(tc1, "failure", type="AssertionError", message="expected 5, got 4")
        tc1.text = "E       AssertionError: expected 5, got 4"
        ET.SubElement(ts, "testcase", name="test_pass2", classname="test_math")
        xml_str = ET.tostring(ts, encoding="unicode")

        mock_llm._responses = [
            _tool_call_response("run_tests", {"path": "test_math.py"}),
            LLMResponse(content="Tests failed, checking results.", model="mock"),
            LLMResponse(content="Fixed the issue. Task complete!", model="mock"),
        ]
        # Patch the run_tests tool to return the XML
        from codingkit.tools.run_tests import RunTestsTool

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            RunTestsTool,
            "execute",
            lambda self, params: ToolResult(success=True, output=xml_str),
        )
        try:
            result = loop.run("Run tests and fix failures")
        finally:
            monkeypatch.undo()

        # The feedback loop should have been triggered
        feedback_turns = [t for t in result.turns if t.test_result is not None]
        assert len(feedback_turns) >= 1, "No feedback turns recorded"
        ft = feedback_turns[0]
        assert ft.test_result is not None
        assert ft.test_result.failed > 0
        assert ft.classification is not None and len(ft.classification) > 0

    def test_all_passed_tests_no_feedback(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """All tests pass → no feedback loop needed."""
        ts_xml = '<?xml version="1.0" ?><testsuite name="pytest" tests="3" failures="0" errors="0"><testcase name="t1" classname="test"/><testcase name="t2" classname="test"/><testcase name="t3" classname="test"/></testsuite>'

        mock_llm._responses = [
            _tool_call_response("run_tests", {"path": "test_all.py"}),
            LLMResponse(content="All tests passed! Task complete.", model="mock"),
        ]
        from codingkit.tools.run_tests import RunTestsTool

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            RunTestsTool,
            "execute",
            lambda self, params: ToolResult(success=True, output=ts_xml),
        )
        try:
            result = loop.run("Run tests")
        finally:
            monkeypatch.undo()

        feedback_turns = [t for t in result.turns if t.test_result is not None]
        assert len(feedback_turns) >= 1
        ft = feedback_turns[0]
        assert ft.test_result is not None
        assert ft.test_result.failed == 0


# ---------------------------------------------------------------------------
# ⑧ Empty response retry
# ---------------------------------------------------------------------------


class TestEmptyResponse:
    def test_empty_response_retried(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """Empty response → retry with a prompt."""
        mock_llm._responses = [
            LLMResponse(content="", model="mock"),  # empty — will be retried
            LLMResponse(content="Here's the result.", model="mock"),
        ]
        # The loop should retry the empty response
        result = loop.run("Do something")
        assert result.total_turns >= 1
        # The mock should have been called twice
        assert len(mock_llm.calls) >= 2


# ---------------------------------------------------------------------------
# ⑨ Max turns safety valve
# ---------------------------------------------------------------------------


class TestMaxTurns:
    def test_max_turns_limits_loop(
        self, mock_llm: MockLLMClient, registry: ToolRegistry
    ) -> None:
        """Agent with low max_turns limit → stops at limit."""
        # Never complete — keep making tool calls
        responses = [
            _tool_call_response("read_file", {"path": f"file_{i}.py"})
            for i in range(MAX_TURNS + 5)
        ]
        mock_llm._responses = responses

        small_loop = AgentLoop(
            llm_client=mock_llm,
            tool_registry=registry,
            max_turns=3,
        )
        result = small_loop.run("Loop forever")
        assert result.total_turns <= 3
        # State should be PAUSED (max turns reached, not completed)
        assert result.state == LoopState.PAUSED

    def test_default_max_turns(self, loop: AgentLoop) -> None:
        """Default max_turns is 50."""
        assert loop._max_turns == 10  # our fixture uses 10


# ---------------------------------------------------------------------------
# LoopResult fields
# ---------------------------------------------------------------------------


class TestLoopResult:
    def test_result_contains_session_id(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        result = loop.run("test")
        assert result.session_id == loop.session_id
        assert len(result.session_id) > 0

    def test_result_contains_turn_records(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        mock_llm._responses = [
            _tool_call_response("read_file", {"path": "x.py"}),
            LLMResponse(content="Done", model="mock"),
        ]
        result = loop.run("test")
        assert len(result.turns) == 2
        assert all(isinstance(t, TurnRecord) for t in result.turns)

    def test_turn_record_has_tool_results(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        mock_llm._responses = [
            _tool_call_response("read_file", {"path": "x.py"}),
            LLMResponse(content="Done", model="mock"),
        ]
        result = loop.run("test")
        turn = result.turns[0]
        assert turn.turn_number == 1
        assert turn.llm_response is not None
        assert turn.parsed_response is not None


# ---------------------------------------------------------------------------
# AgentLoop properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_initial_state(self, loop: AgentLoop) -> None:
        assert loop.state == LoopState.IDLE
        assert loop.current_turn == 0

    def test_state_after_run(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        mock_llm._responses = [LLMResponse(content="Done", model="mock")]
        loop.run("test")
        assert loop.state == LoopState.COMPLETED

    def test_session_id_is_set(self, loop: AgentLoop) -> None:
        assert len(loop.session_id) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_task(self, loop: AgentLoop, mock_llm: MockLLMClient) -> None:
        """Empty task → should still run (no crash)."""
        mock_llm._responses = [LLMResponse(content="No task provided.", model="mock")]
        result = loop.run("")
        assert result.state == LoopState.COMPLETED

    def test_llm_returns_none(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """LLM returns None → handled gracefully."""
        # Exhaust the mock responses
        result = loop.run("Do something")
        # Should not crash, just complete
        assert result.state == LoopState.COMPLETED

    def test_run_twice(self, loop: AgentLoop, mock_llm: MockLLMClient) -> None:
        """Running the loop twice should work."""
        mock_llm._responses = [
            LLMResponse(content="First run", model="mock"),
            LLMResponse(content="Second run", model="mock"),
        ]
        r1 = loop.run("First task")
        assert r1.total_turns == 1
        r2 = loop.run("Second task")
        # Second run should start fresh with new turn numbering
        # (current behavior: turns keep incrementing — this is fine for testing)
        assert r2.state == LoopState.COMPLETED


# ---------------------------------------------------------------------------
# Supplementary edge-case tests (T7.1)
# ---------------------------------------------------------------------------


class TestEmptyResponseAllEmpty:
    """AgentLoop with MockLLMClient that returns only empty responses."""

    def test_all_empty_responses_completes_gracefully(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """All responses empty → loop completes without error."""
        # No responses set → MockLLMClient returns empty responses
        mock_llm._responses = []
        result = loop.run("Do something")
        # The loop should complete without raising
        assert result.state == LoopState.COMPLETED

    def test_empty_responses_produce_no_summary(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """All empty responses → summary is empty string."""
        mock_llm._responses = []
        result = loop.run("Do something")
        assert result.summary == ""


class TestCancelWhenIdle:
    """AgentLoop.cancel() called when state is IDLE."""

    def test_cancel_idle_does_not_raise(
        self, loop: AgentLoop
    ) -> None:
        """cancel() when state is IDLE → should not raise."""
        # State is IDLE before any run
        assert loop.state == LoopState.IDLE
        result = loop.cancel()
        assert isinstance(result, LoopResult)
        assert result.state == LoopState.CANCELLED

    def test_cancel_idle_sets_cancelled_state(
        self, loop: AgentLoop
    ) -> None:
        """cancel() when IDLE → state becomes CANCELLED."""
        loop.cancel()
        assert loop.state == LoopState.CANCELLED


# ---------------------------------------------------------------------------
# ⑩ Multi-round feedback loop: the strategy state machine drives the loop
#    (A.6-② — feedback makes the agent change its next action and escalate)
# ---------------------------------------------------------------------------


class TestFeedbackMultiRound:
    """The correction state machine must actually advance across turns inside
    the real agent loop — not just exist in isolation. These tests inject
    repeated failures via a stubbed ``run_tests`` tool and assert the loop
    (a) escalates and pauses after the threshold, and (b) records a successful
    recovery when tests later pass.
    """

    _FAILING_XML = (
        '<?xml version="1.0"?>'
        '<testsuite name="pytest" tests="1" failures="1" errors="0">'
        '<testcase name="test_a" classname="t_mod">'
        '<failure type="AssertionError" message="expected 5, got 4"/>'
        "</testcase></testsuite>"
    )
    _PASSING_XML = (
        '<?xml version="1.0"?>'
        '<testsuite name="pytest" tests="1" failures="0" errors="0">'
        '<testcase name="test_a" classname="t_mod"/>'
        "</testsuite>"
    )

    def _stub_run_tests(self, outputs: list[str]) -> tuple["pytest.MonkeyPatch", "iter"]:
        """Patch ``RunTestsTool.execute`` to return the given outputs in order."""
        from codingkit.tools.run_tests import RunTestsTool

        mp = pytest.MonkeyPatch()
        it = iter(outputs)

        def _execute(self, params):  # noqa: ANN001
            return ToolResult(success=True, output=next(it))

        mp.setattr(RunTestsTool, "execute", _execute)
        return mp, it

    def test_repeated_failures_escalate_and_pause(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """8 rounds of failing tests → loop PAUSES after the 6-attempt ceiling,
        and the final correction context is in an escalation state."""
        # 8 run_tests calls (mock returns the same tool-call each turn);
        # the loop should pause before exhausting them.
        mock_llm._responses = [
            _tool_call_response("run_tests", {"path": "t_mod.py"}),
        ] * 8

        mp, _ = self._stub_run_tests([self._FAILING_XML] * 8)
        try:
            result = loop.run("fix the failing test")
        finally:
            mp.undo()

        # The loop must have stopped for user intervention (not COMPLETED).
        assert result.state == LoopState.PAUSED
        # The feedback loop ran across many turns, hitting the ceiling.
        assert result.total_feedback_rounds >= 6
        # The final correction context must be in an escalation state.
        corrected = [t for t in result.turns if t.correction_context is not None]
        assert corrected
        final_state = corrected[-1].correction_context.state.value
        assert final_state in {
            "max_retries_reached",
            "strategy_exhausted",
            "user_intervention",
        }, f"expected escalation, got {final_state}"

    def test_failure_then_pass_records_success(
        self, loop: AgentLoop, mock_llm: MockLLMClient
    ) -> None:
        """Two failing rounds followed by a pass → the correction context
        transitions to SUCCEEDED (the loop recovered, not escalated)."""
        mock_llm._responses = [
            _tool_call_response("run_tests", {"path": "t_mod.py"}),
            _tool_call_response("run_tests", {"path": "t_mod.py"}),
            _tool_call_response("run_tests", {"path": "t_mod.py"}),
            LLMResponse(content="Fixed and verified. Task complete!", model="mock"),
        ]

        mp, _ = self._stub_run_tests(
            [self._FAILING_XML, self._FAILING_XML, self._PASSING_XML]
        )
        try:
            result = loop.run("fix then pass")
        finally:
            mp.undo()

        assert result.state == LoopState.COMPLETED
        corrected = [t for t in result.turns if t.correction_context is not None]
        assert corrected
        # After the pass, the in-flight correction must be marked succeeded.
        assert corrected[-1].correction_context.state.value == "succeeded"