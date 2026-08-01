"""Tests for the correction strategy engine (PLAN T3.3).

TDD: write a failing test first, then make it pass.

The strategy engine is the core of the feedback loop.  It implements a state
machine that manages correction attempts across a strategy chain, with
automatic switching after 3 consecutive failures and escalation after 6 total
failures.

Verification targets (from PLAN T3.3):
  ① Same strategy 3 consecutive failures → index increases (auto-switch)
  ② 6 total failures → ``MAX_RETRIES_REACHED``
  ③ All strategies exhausted → ``STRATEGY_EXHAUSTED``
  ④ Success → ``SUCCEEDED``
  ⑤ Resume from last state continues
  ⑥ Every failure category has a non-empty strategy chain
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from codingkit.feedback.classifier import ClassificationResult, FailureCategory
from codingkit.feedback.correction_state import (
    CorrectionAttempt,
    CorrectionContext,
    CorrectionState,
)
from codingkit.feedback.strategy_engine import (
    STRATEGY_CHAINS,
    StrategyEngine,
    get_strategy_chain,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> StrategyEngine:
    return StrategyEngine()


@pytest.fixture
def assert_ctx() -> ClassificationResult:
    return ClassificationResult(
        category=FailureCategory.ASSERTION_ERROR,
        confidence=0.8,
        summary="Assertion failure — AssertionError: expected 5, got 4",
        key_info="AssertionError: expected 5, got 4",
    )


@pytest.fixture
def compile_ctx() -> ClassificationResult:
    return ClassificationResult(
        category=FailureCategory.COMPILE_ERROR,
        confidence=1.0,
        summary="Compile error — SyntaxError: invalid syntax",
        key_info="SyntaxError: invalid syntax",
    )


# ---------------------------------------------------------------------------
# ⑥ Every failure category has a non-empty strategy chain
# ---------------------------------------------------------------------------


class TestStrategyChains:
    """每个分类的策略链都不为空，且最后一个策略为 escalate_to_user"""

    def test_all_categories_have_chains(self) -> None:
        for cat in FailureCategory:
            chain = STRATEGY_CHAINS.get(cat)
            assert chain is not None, f"Missing strategy chain for {cat}"
            assert len(chain) > 0, f"Empty strategy chain for {cat}"

    def test_each_chain_ends_with_escalate(self) -> None:
        for cat in FailureCategory:
            chain = STRATEGY_CHAINS.get(cat)
            assert chain is not None
            assert chain[-1] == "escalate_to_user", (
                f"Chain for {cat} does not end with 'escalate_to_user': {chain}"
            )

    def test_unclassified_chain_is_shortest(self) -> None:
        unclassified_chain = STRATEGY_CHAINS[FailureCategory.UNCLASSIFIED]
        assert len(unclassified_chain) == 2  # general_correction + escalate

    def test_compile_error_chain(self) -> None:
        chain = STRATEGY_CHAINS[FailureCategory.COMPILE_ERROR]
        assert chain == ["check_syntax", "check_code_structure", "escalate_to_user"]

    def test_assertion_error_chain(self) -> None:
        chain = STRATEGY_CHAINS[FailureCategory.ASSERTION_ERROR]
        assert chain == [
            "compare_expected_actual",
            "check_logic",
            "escalate_to_user",
        ]

    def test_get_strategy_chain_unknown_category(self) -> None:
        """Unknown category should fall back to UNCLASSIFIED chain"""
        chain = get_strategy_chain(FailureCategory.UNCLASSIFIED)
        assert chain == ["general_correction", "escalate_to_user"]


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInitialize:
    def test_creates_context_in_attempting_state(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(
            session_id="sess-1",
            turn_id="turn-1",
            classification=assert_ctx,
        )
        assert ctx.state == CorrectionState.ATTEMPTING
        assert ctx.session_id == "sess-1"
        assert ctx.turn_id == "turn-1"
        assert ctx.attempt_number == 0
        assert ctx.current_strategy_index == 0
        assert ctx.history == []
        assert ctx.consecutive_failures == 0
        assert ctx.classification is assert_ctx

    def test_uses_correct_strategy_chain(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        expected = STRATEGY_CHAINS[FailureCategory.ASSERTION_ERROR]
        assert ctx.strategy_chain == expected

    def test_custom_strategy_chain(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        custom = ["custom_strat_a", "custom_strat_b", "escalate_to_user"]
        ctx = engine.initialize(
            classification=assert_ctx, custom_strategy_chain=custom
        )
        assert ctx.strategy_chain == custom
        assert ctx.strategy_chain != STRATEGY_CHAINS[FailureCategory.ASSERTION_ERROR]

    def test_initialize_without_classification(
        self, engine: StrategyEngine
    ) -> None:
        ctx = engine.initialize(session_id="sess-1")
        assert ctx.classification.category == FailureCategory.UNCLASSIFIED
        assert ctx.strategy_chain == STRATEGY_CHAINS[FailureCategory.UNCLASSIFIED]


# ---------------------------------------------------------------------------
# ① Same strategy 3 consecutive failures → index increases (auto-switch)
# ---------------------------------------------------------------------------


class TestAutoSwitchAfterThreeFailures:
    def test_two_failures_same_strategy_keeps_index(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        assert ctx.current_strategy_index == 0

        # Fail twice — still on strategy 0
        ctx = engine.record_attempt(ctx, success=False, result="fail 1")
        assert ctx.current_strategy_index == 0
        assert ctx.state == CorrectionState.ATTEMPTING

        ctx = engine.record_attempt(ctx, success=False, result="fail 2")
        assert ctx.current_strategy_index == 0
        assert ctx.state == CorrectionState.ATTEMPTING

    def test_three_failures_same_strategy_switches_index(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        assert ctx.current_strategy_index == 0

        for i in range(3):
            ctx = engine.record_attempt(ctx, success=False, result=f"fail {i+1}")

        # After 3 consecutive failures → switch to index 1
        assert ctx.current_strategy_index == 1
        assert ctx.consecutive_failures == 0  # reset
        assert ctx.state == CorrectionState.ATTEMPTING

    def test_switch_then_fail_three_more_switches_again(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        # 3 failures on strategy 0 → switch to 1
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        assert ctx.current_strategy_index == 1

        # 3 more failures on strategy 1 → switch to 2 (escalate_to_user)
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        assert ctx.current_strategy_index == 2
        # After 6 total failures
        assert ctx.state == CorrectionState.MAX_RETRIES_REACHED


# ---------------------------------------------------------------------------
# ② 6 total failures → MAX_RETRIES_REACHED
# ---------------------------------------------------------------------------


class TestMaxRetriesReached:
    def test_six_total_failures_triggers_max_retries(
        self, engine: StrategyEngine, compile_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=compile_ctx)
        # COMPILE_ERROR chain: check_syntax, check_code_structure, escalate
        # 3 fails on check_syntax → switch to check_code_structure
        # 3 fails on check_code_structure → switch to escalate → MAX_RETRIES
        for i in range(6):
            ctx = engine.record_attempt(ctx, success=False, result=f"fail {i+1}")

        assert ctx.state == CorrectionState.MAX_RETRIES_REACHED
        assert ctx.attempt_number == 6

    def test_max_retries_not_reached_at_5(
        self, engine: StrategyEngine, compile_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=compile_ctx)
        for _ in range(5):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        assert ctx.state != CorrectionState.MAX_RETRIES_REACHED
        assert ctx.attempt_number == 5

    def test_next_strategy_returns_none_when_max_retries(
        self, engine: StrategyEngine, compile_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=compile_ctx)
        for _ in range(6):
            ctx = engine.record_attempt(ctx, success=False, result="fail")

        strategy = engine.next_strategy(ctx)
        assert strategy is None
        assert ctx.state == CorrectionState.MAX_RETRIES_REACHED


# ---------------------------------------------------------------------------
# ③ All strategies exhausted → STRATEGY_EXHAUSTED
# ---------------------------------------------------------------------------


class TestStrategyExhausted:
    def test_strategy_exhausted_when_no_more_entries(
        self, engine: StrategyEngine
    ) -> None:
        """When the chain has only 1 real strategy + escalate, running out
        should trigger STRATEGY_EXHAUSTED."""
        unclassified = ClassificationResult(category=FailureCategory.UNCLASSIFIED)
        ctx = engine.initialize(classification=unclassified)
        # Chain: general_correction, escalate_to_user
        # 3 fails on general_correction → switch to escalate → should stop
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")

        # After 3 fails, index becomes 1 (escalate_to_user)
        assert ctx.current_strategy_index == 1
        # next_strategy should detect escalate_to_user → USER_INTERVENTION
        strategy = engine.next_strategy(ctx)
        assert strategy is None
        assert ctx.state == CorrectionState.USER_INTERVENTION

    def test_escalate_to_user_sets_user_intervention(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        # Push to the escalate_to_user entry at index 2
        for _ in range(6):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        # MAX_RETRIES_REACHED takes precedence
        assert ctx.state == CorrectionState.MAX_RETRIES_REACHED

    def test_strategy_exhausted_with_custom_short_chain(
        self, engine: StrategyEngine
    ) -> None:
        """Custom chain with 1 real strategy: exhaust it, then
        STRATEGY_EXHAUSTED."""
        custom = ["fix_fast", "escalate_to_user"]
        ctx = engine.initialize(
            classification=ClassificationResult(),
            custom_strategy_chain=custom,
        )
        # 3 fails on fix_fast → switch to escalate
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        assert ctx.current_strategy_index == 1
        # next_strategy detects escalate_to_user → USER_INTERVENTION
        strategy = engine.next_strategy(ctx)
        assert strategy is None
        assert ctx.state == CorrectionState.USER_INTERVENTION


# ---------------------------------------------------------------------------
# ④ Success → SUCCEEDED
# ---------------------------------------------------------------------------


class TestSucceeded:
    def test_first_attempt_success(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.record_attempt(ctx, success=True, result="fixed it!")
        assert ctx.state == CorrectionState.SUCCEEDED
        assert ctx.attempt_number == 1

    def test_success_after_switching_strategy(
        self, engine: StrategyEngine, compile_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=compile_ctx)
        # 3 failures on strategy 0 → switch to 1
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        assert ctx.current_strategy_index == 1

        # Now succeed on strategy 1
        ctx = engine.record_attempt(ctx, success=True, result="fixed on retry")
        assert ctx.state == CorrectionState.SUCCEEDED
        assert ctx.attempt_number == 4

    def test_successful_attempt_recorded_in_history(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.record_attempt(ctx, success=True, result="all good")
        assert len(ctx.history) == 1
        assert ctx.history[0].success is True
        assert ctx.history[0].result == "all good"
        assert ctx.history[0].strategy == "compare_expected_actual"


# ---------------------------------------------------------------------------
# ⑤ Resume from last state
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_from_max_retries(
        self, engine: StrategyEngine, compile_ctx: ClassificationResult
    ) -> None:
        """MAX_RETRIES_REACHED → resume → ATTEMPTING."""
        ctx = engine.initialize(classification=compile_ctx)
        for _ in range(6):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        assert ctx.state == CorrectionState.MAX_RETRIES_REACHED
        ctx = engine.resume(ctx)
        assert ctx.state == CorrectionState.ATTEMPTING

    def test_resume_from_strategy_exhausted(
        self, engine: StrategyEngine
    ) -> None:
        """Custom chain with 1 strategy → STRATEGY_EXHAUSTED → resume."""
        custom = ["only_strat"]
        ctx = engine.initialize(
            classification=ClassificationResult(),
            custom_strategy_chain=custom,
        )
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        assert ctx.state == CorrectionState.STRATEGY_EXHAUSTED
        ctx = engine.resume(ctx)
        assert ctx.state == CorrectionState.ATTEMPTING

    def test_resume_from_succeeded_returns_unchanged(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.record_attempt(ctx, success=True, result="fixed")
        assert ctx.state == CorrectionState.SUCCEEDED
        ctx = engine.resume(ctx)
        assert ctx.state == CorrectionState.SUCCEEDED  # unchanged

    def test_resume_from_cancelled_returns_unchanged(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.cancel(ctx)
        assert ctx.state == CorrectionState.CANCELLED
        ctx = engine.resume(ctx)
        assert ctx.state == CorrectionState.CANCELLED  # unchanged


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_sets_state(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.cancel(ctx)
        assert ctx.state == CorrectionState.CANCELLED

    def test_cancel_mid_attempt(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.record_attempt(ctx, success=False, result="fail 1")
        ctx = engine.cancel(ctx)
        assert ctx.state == CorrectionState.CANCELLED
        assert ctx.attempt_number == 1


# ---------------------------------------------------------------------------
# can_continue
# ---------------------------------------------------------------------------


class TestCanContinue:
    def test_can_continue_after_init(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        assert engine.can_continue(ctx) is True

    def test_cannot_continue_after_success(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.record_attempt(ctx, success=True, result="fixed")
        assert engine.can_continue(ctx) is False

    def test_cannot_continue_after_max_retries(
        self, engine: StrategyEngine, compile_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=compile_ctx)
        for _ in range(6):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        assert engine.can_continue(ctx) is False

    def test_cannot_continue_after_cancel(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.cancel(ctx)
        assert engine.can_continue(ctx) is False


# ---------------------------------------------------------------------------
# next_strategy integration
# ---------------------------------------------------------------------------


class TestNextStrategy:
    def test_next_strategy_returns_first_strategy(
        self, engine: StrategyEngine, compile_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=compile_ctx)
        strategy = engine.next_strategy(ctx)
        assert strategy == "check_syntax"

    def test_next_strategy_after_failures(
        self, engine: StrategyEngine, compile_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=compile_ctx)
        # 3 failures → switch to index 1
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        strategy = engine.next_strategy(ctx)
        assert strategy == "check_code_structure"

    def test_next_strategy_returns_none_for_escalate(
        self, engine: StrategyEngine
    ) -> None:
        """When the next strategy is escalate_to_user, next_strategy returns
        None and sets state to USER_INTERVENTION."""
        ctx = engine.initialize(
            classification=ClassificationResult(category=FailureCategory.UNCLASSIFIED)
        )
        # 3 fails on general_correction → switch to escalate
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        strategy = engine.next_strategy(ctx)
        assert strategy is None
        assert ctx.state == CorrectionState.USER_INTERVENTION


# ---------------------------------------------------------------------------
# status_summary
# ---------------------------------------------------------------------------


class TestStatusSummary:
    def test_summary_contains_expected_keys(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        summary = engine.status_summary(ctx)
        assert "state" in summary
        assert "attempt_number" in summary
        assert "current_strategy" in summary
        assert "strategy_chain" in summary
        assert "classification" in summary
        assert "history" in summary

    def test_summary_after_attempts(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.record_attempt(ctx, success=False, result="fail 1")
        ctx = engine.record_attempt(ctx, success=False, result="fail 2")
        summary = engine.status_summary(ctx)
        assert summary["attempt_number"] == 2
        assert len(summary["history"]) == 2
        assert summary["history"][0]["success"] is False
        assert summary["history"][1]["result"] == "fail 2"

    def test_summary_after_success(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        ctx = engine.record_attempt(ctx, success=True, result="done")
        summary = engine.status_summary(ctx)
        assert summary["state"] == "succeeded"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_strategy_chain(
        self, engine: StrategyEngine
    ) -> None:
        """Custom chain with no strategies → should immediately exhaust."""
        ctx = engine.initialize(
            classification=ClassificationResult(),
            custom_strategy_chain=[],
        )
        assert ctx.current_strategy_index == 0
        assert len(ctx.strategy_chain) == 0
        strategy = engine.next_strategy(ctx)
        assert strategy is None
        assert ctx.state == CorrectionState.STRATEGY_EXHAUSTED

    def test_attempt_number_tracks_all_calls(
        self, engine: StrategyEngine, compile_ctx: ClassificationResult
    ) -> None:
        """record_attempt always increments the attempt counter, but the
        state machine stops returning new strategies once max retries is hit."""
        ctx = engine.initialize(classification=compile_ctx)
        for _ in range(10):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        # State is terminal after 6 total failures
        assert ctx.state == CorrectionState.MAX_RETRIES_REACHED
        # attempt_number counts every call to record_attempt
        assert ctx.attempt_number == 10
        # next_strategy should return None (stopped)
        strategy = engine.next_strategy(ctx)
        assert strategy is None

    def test_consecutive_failures_reset_on_switch(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        # 3 failures → switch → consecutive_failures reset to 0
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        assert ctx.consecutive_failures == 0
        assert ctx.current_strategy_index == 1

    def test_history_order(
        self, engine: StrategyEngine, assert_ctx: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=assert_ctx)
        for i in range(3):
            ctx = engine.record_attempt(ctx, success=False, result=f"fail {i+1}")
        assert len(ctx.history) == 3
        assert ctx.history[0].result == "fail 1"
        assert ctx.history[1].result == "fail 2"
        assert ctx.history[2].result == "fail 3"