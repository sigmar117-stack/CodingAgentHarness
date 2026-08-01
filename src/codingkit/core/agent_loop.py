"""Agent main loop — orchestrates the build → call → parse → act → feedback cycle (PLAN T4.1).

The ``AgentLoop`` is the central orchestrator of CodingKit.  It integrates all
Layer-2 and Layer-3 modules into a single loop:

1. **Context Builder** — assembles system prompt, task, memories, history, feedback.
2. **LLM Client** — calls the configured LLM (Claude, OpenAI, or Mock).
3. **Response Parser** — extracts text replies or tool calls from the LLM.
4. **Guardrail** — intercepts dangerous actions (HITL approval).
5. **Tool Executor** — runs approved tools and captures results.
6. **Feedback Loop** — when tests run, feeds results through validator →
   classifier → strategy engine → ingester.

The loop can be run in two modes:

* ``run(task)`` — full automatic loop until completion or interruption.
* ``step()`` — single turn for testing and interactive use.

It supports ``cancel()`` and ``resume()`` for session management.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from codingkit.core.context_builder import ContextBuilder
from codingkit.core.llm_client import LLMClient, LLMResponse, MockLLMClient, ToolCall
from codingkit.core.response_parser import ParsedResponse, ResponseParser
from codingkit.feedback.classifier import (
    ClassificationResult,
    FailureCategory,
    classify,
)
from codingkit.feedback.correction_state import (
    CorrectionContext,
    CorrectionState,
)
from codingkit.feedback.ingester import FeedbackContext, build_feedback_prompt
from codingkit.feedback.strategy_engine import StrategyEngine
from codingkit.feedback.validator import TestResult, parse_junit_xml, parse_raw_output
from codingkit.governance.approval import ApprovalDecision, ApprovalHandler
from codingkit.governance.guardrail import Guardrail, GuardrailResult
from codingkit.memory.memory_manager import MemoryManager
from codingkit.tools.base import RiskLevel, ToolResult
from codingkit.tools.registry import ToolRegistry


__all__ = [
    "AgentLoop",
    "LoopState",
    "TurnRecord",
    "MAX_TURNS",
]


#: Safety valve — maximum turns before the loop auto-stops.
MAX_TURNS = 50


# ---------------------------------------------------------------------------
# LoopState
# ---------------------------------------------------------------------------


class LoopState(Enum):
    """Lifecycle state of the agent loop."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"  # waiting for user input (approval or task complete)
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"


# ---------------------------------------------------------------------------
# TurnRecord
# ---------------------------------------------------------------------------


@dataclass
class TurnRecord:
    """Record of a single turn in the agent loop."""

    __test__ = False

    turn_number: int
    llm_request: List[Dict[str, Any]] = field(default_factory=list)
    llm_response: Optional[LLMResponse] = None
    parsed_response: Optional[ParsedResponse] = None
    tool_results: List[ToolResult] = field(default_factory=list)
    guardrail_result: Optional[GuardrailResult] = None
    approval_decision: Optional[ApprovalDecision] = None
    test_result: Optional[TestResult] = None
    classification: Optional[List[ClassificationResult]] = None
    correction_context: Optional[CorrectionContext] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# AgentLoop
# ---------------------------------------------------------------------------


class AgentLoop:
    """Central orchestrator — the agent main loop.

    Usage::

        loop = AgentLoop(
            llm_client=my_llm,
            tool_registry=ToolRegistry(),
        )
        result = loop.run("Write a test for the calculator")
        print(result.summary)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        tool_registry: Optional[ToolRegistry] = None,
        memory_manager: Optional[MemoryManager] = None,
        guardrail: Optional[Guardrail] = None,
        approval_handler: Optional[ApprovalHandler] = None,
        context_builder: Optional[ContextBuilder] = None,
        response_parser: Optional[ResponseParser] = None,
        strategy_engine: Optional[StrategyEngine] = None,
        max_turns: int = MAX_TURNS,
        session_id: Optional[str] = None,
        on_turn_complete: Optional[Callable[[TurnRecord], None]] = None,
    ) -> None:
        """Initialize the agent loop.

        Args:
            llm_client: The LLM client to use for generation.
            tool_registry: Registry of available tools.  Defaults to a fresh
                registry with all 10 tools.
            memory_manager: Memory manager for cross-session memory.
                Defaults to a fresh ``MemoryManager``.
            guardrail: Guardrail for dangerous-action detection.  Defaults to
                a fresh ``Guardrail``.
            approval_handler: HITL approval handler.  Defaults to a fresh
                handler with 120s timeout.
            context_builder: Context builder for assembling LLM messages.
                Defaults to a fresh ``ContextBuilder``.
            response_parser: Response parser for LLM output.  Defaults to
                a fresh ``ResponseParser``.
            strategy_engine: Strategy engine for correction feedback.
                Defaults to a fresh ``StrategyEngine``.
            max_turns: Maximum number of turns before auto-stop.
            session_id: Optional session identifier.  Auto-generated if not
                provided.
            on_turn_complete: Optional callback invoked after each turn
                completes (useful for logging and WebUI updates).
        """
        self._llm = llm_client
        self._tool_registry = tool_registry or ToolRegistry()
        self._memory = memory_manager or MemoryManager()
        self._guardrail = guardrail or Guardrail()
        self._approval = approval_handler or ApprovalHandler()
        self._context_builder = context_builder or ContextBuilder(self._tool_registry)
        self._parser = response_parser or ResponseParser()
        self._strategy_engine = strategy_engine or StrategyEngine()
        self._max_turns = max_turns
        self._session_id = session_id or str(uuid.uuid4())
        self._on_turn_complete = on_turn_complete

        # Runtime state
        self._state: LoopState = LoopState.IDLE
        self._task: str = ""
        self._history: List[Dict[str, Any]] = []
        self._turns: List[TurnRecord] = []
        self._current_turn: int = 0
        self._feedback_ctx: Optional[FeedbackContext] = None
        self._correction_ctx: Optional[CorrectionContext] = None
        self._last_test_result: Optional[TestResult] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> LoopState:
        return self._state

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def turns(self) -> List[TurnRecord]:
        return list(self._turns)

    @property
    def task(self) -> str:
        return self._task

    @property
    def current_turn(self) -> int:
        return self._current_turn

    # ------------------------------------------------------------------
    # Main public API
    # ------------------------------------------------------------------

    def run(self, task: str) -> "LoopResult":
        """Run the agent loop to completion on *task*.

        This is a blocking call that runs the full loop.  For interactive
        control, use ``step()`` instead.

        Args:
            task: The user's task description.

        Returns:
            A ``LoopResult`` with the outcome summary.
        """
        self._task = task
        self._state = LoopState.RUNNING
        self._current_turn = 0

        while self._state == LoopState.RUNNING:
            self._current_turn += 1
            if self._current_turn > self._max_turns:
                self._state = LoopState.PAUSED
                break

            turn = self._step()
            self._turns.append(turn)
            if self._on_turn_complete:
                self._on_turn_complete(turn)

            # Check for terminal states
            if self._state == LoopState.CANCELLED:
                break

            parsed = turn.parsed_response
            if parsed is not None:
                # Stop if the LLM explicitly says it's done
                if parsed.is_complete:
                    self._state = LoopState.COMPLETED
                    break
                # Stop if the LLM returned text without tool calls (responding to user)
                if parsed.text and not parsed.tool_calls:
                    self._state = LoopState.COMPLETED
                    break
                # Stop if the LLM returned nothing at all (exhausted)
                if not parsed.text and not parsed.tool_calls:
                    self._state = LoopState.COMPLETED
                    break
            else:
                # No parsed response at all → stop
                self._state = LoopState.COMPLETED
                break

        return self._build_result()

    def step(self, user_input: str = "") -> TurnRecord:
        """Execute a single turn of the loop.

        This is useful for interactive/stepped control and testing.

        Args:
            user_input: Optional user input to inject (e.g., approval decision
                or new instructions).

        Returns:
            The ``TurnRecord`` for this turn.
        """
        if self._state == LoopState.IDLE:
            self._state = LoopState.RUNNING

        self._current_turn += 1
        turn = self._step(user_input=user_input)
        self._turns.append(turn)

        if turn.parsed_response and turn.parsed_response.is_complete:
            self._state = LoopState.COMPLETED

        if self._on_turn_complete:
            self._on_turn_complete(turn)

        return turn

    def cancel(self) -> "LoopResult":
        """Cancel the current run and return the result so far."""
        self._state = LoopState.CANCELLED
        return self._build_result()

    def resume(
        self,
        task: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        turns: Optional[List[TurnRecord]] = None,
    ) -> None:
        """Resume from a previously saved state.

        Args:
            task: The task to continue (uses the stored task if ``None``).
            history: Previous message history to restore.
            turns: Previous turn records to restore.
        """
        if task is not None:
            self._task = task
        if history is not None:
            self._history = history
        if turns is not None:
            self._turns = list(turns)
            self._current_turn = len(turns)

        if self._state in (LoopState.CANCELLED, LoopState.COMPLETED, LoopState.ERROR):
            self._state = LoopState.PAUSED

    # ------------------------------------------------------------------
    # Internal: single turn
    # ------------------------------------------------------------------

    def _step(self, user_input: str = "") -> TurnRecord:
        """Execute one full turn: build context → call LLM → parse → act."""
        turn = TurnRecord(turn_number=self._current_turn)

        # --- 1. Build context ---
        memories = self._memory.recall(self._task, n_results=3) if self._task else []
        messages = self._context_builder.build(
            task=self._task,
            history=self._history,
            memories=memories if memories else None,
            feedback_ctx=self._feedback_ctx,
        )
        # Inject user input if provided
        if user_input:
            messages.append({"role": "user", "content": user_input})

        turn.llm_request = list(messages)
        tool_defs = self._context_builder.tool_definitions()

        # --- 2. Call LLM ---
        llm_response = self._llm.generate(messages, tools=tool_defs)
        turn.llm_response = llm_response

        # --- 3. Parse response ---
        parsed = self._parser.parse(llm_response)
        turn.parsed_response = parsed

        # Handle empty response with retry
        if self._parser.needs_retry(parsed) and self._current_turn <= 3:
            retry_msg = self._parser.retry_prompt(self._current_turn)
            messages.append({"role": "user", "content": retry_msg})
            llm_response = self._llm.generate(messages, tools=tool_defs)
            parsed = self._parser.parse(llm_response)
            turn.llm_response = llm_response
            turn.parsed_response = parsed

        # --- 4. Process tool calls (if any) ---
        if parsed.tool_calls:
            for tc in parsed.tool_calls:
                tool_result = self._execute_tool(tc, turn)
                turn.tool_results.append(tool_result)

                # If the tool was run_tests, process feedback
                if tc.name == "run_tests" and tool_result.success:
                    self._process_test_results(tool_result, turn)

                # Record the tool result in the message history
                self._history.append({
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": tc.id or "", "name": tc.name, "input": tc.arguments}
                    ],
                })
                self._history.append({
                    "role": "tool",
                    "tool_use_id": tc.id or "",
                    "content": tool_result.output,
                })

        # --- 5. Record text output in history ---
        if parsed.text:
            self._history.append({
                "role": "assistant",
                "content": parsed.text,
            })

        turn.timestamp = datetime.now(timezone.utc)
        return turn

    # ------------------------------------------------------------------
    # Tool execution with guardrail
    # ------------------------------------------------------------------

    def _execute_tool(self, tc: ToolCall, turn: TurnRecord) -> ToolResult:
        """Execute a single tool call, passing through guardrail and approval.

        Args:
            tc: The tool call from the LLM.
            turn: The current turn record (mutated with guardrail/approval info).

        Returns:
            The ``ToolResult`` from execution.
        """
        # --- Guardrail check ---
        guardrail_result = self._guardrail.check(tc)
        turn.guardrail_result = guardrail_result

        if guardrail_result.is_dangerous:
            # --- HITL approval ---
            decision, modified_params = self._approval.request_approval(tc)
            turn.approval_decision = decision

            if decision == ApprovalDecision.REJECTED:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Action '{tc.name}' was rejected by the user.",
                )

            if decision == ApprovalDecision.MODIFIED and modified_params is not None:
                tc = ToolCall(name=tc.name, arguments=modified_params, id=tc.id)

            # APPROVED: fall through to execution

        # --- Execute tool ---
        tool = self._tool_registry.get(tc.name)
        if tool is None:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tc.name}",
            )

        try:
            return tool.execute(tc.arguments)
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool execution error: {e}",
            )

    # ------------------------------------------------------------------
    # Feedback loop integration
    # ------------------------------------------------------------------

    def _process_test_results(
        self,
        tool_result: ToolResult,
        turn: TurnRecord,
    ) -> None:
        """Process test results through the feedback loop.

        Validates → classifies → runs strategy engine → builds feedback context.
        """
        # --- Parse test result ---
        raw_output = tool_result.output
        test_result: TestResult | None = None

        # Try JUnit XML first, then raw output
        if raw_output.strip().startswith("<?xml") or "<testsuite" in raw_output:
            test_result = parse_junit_xml(raw_output, raw_output=raw_output)
        else:
            test_result = parse_raw_output(raw_output)

        turn.test_result = test_result

        # Only process feedback if there are failures
        if test_result.failed == 0 and test_result.errors == 0:
            return

        # --- Classify failures ---
        classifications = classify(test_result)
        turn.classification = classifications

        # --- Run strategy engine ---
        if classifications:
            primary = classifications[0]
            self._correction_ctx = self._strategy_engine.initialize(
                session_id=self._session_id,
                turn_id=str(turn.turn_number),
                classification=primary,
            )
            turn.correction_context = self._correction_ctx

            # Get next strategy
            strategy = self._strategy_engine.next_strategy(self._correction_ctx)

            # --- Build feedback context ---
            self._feedback_ctx = FeedbackContext(
                original_code="",  # Would come from the task context
                test_results=test_result,
                classification=primary,
                correction_history=self._correction_ctx,
                current_strategy=strategy,
            )

    # ------------------------------------------------------------------
    # Result building
    # ------------------------------------------------------------------

    def _build_result(self) -> "LoopResult":
        """Build a ``LoopResult`` from the current state."""
        # Extract summary from the last assistant message in history
        summary_parts: List[str] = []
        for msg in reversed(self._history):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    summary_parts.append(content[:500])
                    break
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text.strip():
                                summary_parts.append(text[:500])
                                break

        tool_calls_count = sum(len(t.tool_results) for t in self._turns)
        feedback_count = sum(
            1 for t in self._turns if t.test_result is not None
        )

        return LoopResult(
            session_id=self._session_id,
            state=self._state,
            total_turns=len(self._turns),
            total_tool_calls=tool_calls_count,
            total_feedback_rounds=feedback_count,
            summary="\n".join(summary_parts),
            turns=list(self._turns),
            history=list(self._history),
        )


# ---------------------------------------------------------------------------
# LoopResult
# ---------------------------------------------------------------------------


@dataclass
class LoopResult:
    """Result of an agent loop run.

    Attributes:
        session_id: The session identifier.
        state: Final state of the loop.
        total_turns: Number of turns executed.
        total_tool_calls: Total tool calls made.
        total_feedback_rounds: Total feedback-loop invocations.
        summary: Text summary of the result.
        turns: All turn records (for inspection/debugging).
        history: Full message history (for session persistence).
    """

    __test__ = False

    session_id: str = ""
    state: LoopState = LoopState.IDLE
    total_turns: int = 0
    total_tool_calls: int = 0
    total_feedback_rounds: int = 0
    summary: str = ""
    turns: List[TurnRecord] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)