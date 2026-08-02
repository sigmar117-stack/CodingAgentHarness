"""Tests for the feedback ingester (PLAN T3.4).

TDD: write a failing test first, then make it pass.

The ingester formats correction history into a structured Markdown prompt for
the LLM.  It must handle:

* Full correction history → all key sections present
* Empty history → basic structure still present
* Long history → truncation to MAX_HISTORY_ROUNDS
* Output format is valid structured text
* All states (ATTEMPTING, SUCCEEDED, MAX_RETRIES, etc.)
"""

from __future__ import annotations

import pytest

from codingkit.feedback.classifier import ClassificationResult, FailureCategory
from codingkit.feedback.correction_state import (
    CorrectionContext,
    CorrectionState,
)
from codingkit.feedback.ingester import (
    MAX_HISTORY_ROUNDS,
    FeedbackContext,
    build_feedback_prompt,
)
from codingkit.feedback.strategy_engine import StrategyEngine
from codingkit.feedback.validator import FailureDetail, TestResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> StrategyEngine:
    return StrategyEngine()


@pytest.fixture
def sample_test_result() -> TestResult:
    return TestResult(
        total=5,
        passed=3,
        failed=1,
        errors=1,
        failures=[
            FailureDetail(
                test_name="test_math::test_add",
                error_type="AssertionError",
                error_message="expected 5, got 4",
                traceback="E       AssertionError: expected 5, got 4\n"
                "test_math.py:12: in test_add\n"
                "    assert add(2, 2) == 5",
            ),
        ],
        raw_output="FAILED test_math.py::test_add - AssertionError: expected 5, got 4",
    )


@pytest.fixture
def sample_classification() -> ClassificationResult:
    return ClassificationResult(
        category=FailureCategory.ASSERTION_ERROR,
        confidence=0.8,
        summary="Assertion failure — AssertionError: expected 5, got 4",
        key_info="AssertionError: expected 5, got 4",
    )


# ---------------------------------------------------------------------------
# ① Full correction history → all key sections present
# ---------------------------------------------------------------------------


class TestFullHistory:
    def test_prompt_contains_all_sections(
        self,
        engine: StrategyEngine,
        sample_test_result: TestResult,
        sample_classification: ClassificationResult,
    ) -> None:
        ctx = engine.initialize(classification=sample_classification)
        ctx = engine.record_attempt(ctx, success=False, result="Tried fixing logic")
        ctx = engine.record_attempt(ctx, success=True, result="Fixed the comparison")

        fc = FeedbackContext(
            original_code="def add(a, b):\n    return a + b",
            test_results=sample_test_result,
            classification=sample_classification,
            correction_history=ctx,
            current_strategy="check_logic",
        )
        prompt = build_feedback_prompt(fc)

        # All sections present
        assert "# CodingKit Feedback" in prompt
        assert "Original Code" in prompt
        assert "Test Results" in prompt
        assert "Failure Classification" in prompt
        assert "Correction History" in prompt
        assert "Next Strategy" in prompt
        assert "check_logic" in prompt

    def test_prompt_contains_test_failure_details(
        self,
        engine: StrategyEngine,
        sample_test_result: TestResult,
        sample_classification: ClassificationResult,
    ) -> None:
        ctx = engine.initialize(classification=sample_classification)
        fc = FeedbackContext(
            original_code="",
            test_results=sample_test_result,
            classification=sample_classification,
            correction_history=ctx,
            current_strategy="compare_expected_actual",
        )
        prompt = build_feedback_prompt(fc)

        assert "test_math::test_add" in prompt
        assert "AssertionError" in prompt
        assert "expected 5, got 4" in prompt
        assert "5" in prompt  # total count
        assert "3" in prompt  # passed count

    def test_prompt_contains_classification(
        self,
        engine: StrategyEngine,
        sample_test_result: TestResult,
        sample_classification: ClassificationResult,
    ) -> None:
        ctx = engine.initialize(classification=sample_classification)
        fc = FeedbackContext(
            test_results=sample_test_result,
            classification=sample_classification,
            correction_history=ctx,
        )
        prompt = build_feedback_prompt(fc)

        assert "assertion_error" in prompt
        assert "0.80" in prompt or "0.8" in prompt
        assert "Assertion failure" in prompt


# ---------------------------------------------------------------------------
# ② Empty history → basic structure still present
# ---------------------------------------------------------------------------


class TestEmptyHistory:
    def test_no_correction_history(
        self,
        sample_test_result: TestResult,
        sample_classification: ClassificationResult,
    ) -> None:
        """No correction attempts yet → still produces a valid prompt."""
        ctx = CorrectionContext(
            state=CorrectionState.ATTEMPTING,
            strategy_chain=["general_correction", "escalate_to_user"],
        )
        fc = FeedbackContext(
            test_results=sample_test_result,
            classification=sample_classification,
            correction_history=ctx,
        )
        prompt = build_feedback_prompt(fc)

        assert "# CodingKit Feedback" in prompt
        assert "Test Results" in prompt
        assert "Failure Classification" in prompt
        assert "Correction History" in prompt
        assert "No correction attempts yet" in prompt

    def test_no_original_code(
        self,
        sample_test_result: TestResult,
        sample_classification: ClassificationResult,
    ) -> None:
        """No original code → that section is omitted."""
        fc = FeedbackContext(
            original_code="",
            test_results=sample_test_result,
            classification=sample_classification,
        )
        prompt = build_feedback_prompt(fc)
        assert "Original Code" not in prompt

    def test_no_current_strategy(
        self,
        sample_test_result: TestResult,
        sample_classification: ClassificationResult,
    ) -> None:
        """No current strategy → the Next Strategy section is omitted."""
        fc = FeedbackContext(
            test_results=sample_test_result,
            classification=sample_classification,
        )
        prompt = build_feedback_prompt(fc)
        assert "Next Strategy" not in prompt


# ---------------------------------------------------------------------------
# ③ Long history → truncation
# ---------------------------------------------------------------------------


class TestTruncation:
    def test_history_truncated_to_max_rounds(
        self, engine: StrategyEngine, sample_classification: ClassificationResult
    ) -> None:
        """More than MAX_HISTORY_ROUNDS attempts → only the most recent shown."""
        ctx = engine.initialize(classification=sample_classification)
        for i in range(MAX_HISTORY_ROUNDS + 3):
            ctx = engine.record_attempt(ctx, success=False, result=f"fail {i+1}")

        fc = FeedbackContext(
            classification=sample_classification,
            correction_history=ctx,
        )
        prompt = build_feedback_prompt(fc)

        # Should mention truncation
        assert "Showing the" in prompt
        assert str(MAX_HISTORY_ROUNDS) in prompt

    def test_short_history_not_truncated(
        self, engine: StrategyEngine, sample_classification: ClassificationResult
    ) -> None:
        """Fewer than MAX_HISTORY_ROUNDS → all attempts shown."""
        ctx = engine.initialize(classification=sample_classification)
        for i in range(2):
            ctx = engine.record_attempt(ctx, success=False, result=f"fail {i+1}")

        fc = FeedbackContext(
            classification=sample_classification,
            correction_history=ctx,
        )
        prompt = build_feedback_prompt(fc)

        assert "Showing the" not in prompt
        assert "fail 1" in prompt
        assert "fail 2" in prompt


# ---------------------------------------------------------------------------
# ④ Output format
# ---------------------------------------------------------------------------


class TestOutputFormat:
    def test_prompt_is_valid_markdown(
        self,
        engine: StrategyEngine,
        sample_test_result: TestResult,
        sample_classification: ClassificationResult,
    ) -> None:
        """Basic structure: headers, lists, code blocks."""
        ctx = engine.initialize(classification=sample_classification)
        fc = FeedbackContext(
            original_code="def f(): pass",
            test_results=sample_test_result,
            classification=sample_classification,
            correction_history=ctx,
            current_strategy="check_logic",
        )
        prompt = build_feedback_prompt(fc)

        # Markdown headers (##)
        assert "## Test Results" in prompt
        assert "## Failure Classification" in prompt
        assert "## Correction History" in prompt
        assert "## Next Strategy" in prompt

        # Code blocks
        assert "```" in prompt

        # Bold markers
        assert "**" in prompt

        # Lists
        assert "- " in prompt

    def test_prompt_is_not_empty(
        self,
        sample_test_result: TestResult,
        sample_classification: ClassificationResult,
    ) -> None:
        fc = FeedbackContext(
            test_results=sample_test_result,
            classification=sample_classification,
        )
        prompt = build_feedback_prompt(fc)
        assert len(prompt) > 50


# ---------------------------------------------------------------------------
# State-specific handling
# ---------------------------------------------------------------------------


class TestStateSpecific:
    def test_succeeded_state_message(
        self, engine: StrategyEngine, sample_classification: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=sample_classification)
        ctx = engine.record_attempt(ctx, success=True, result="fixed")
        fc = FeedbackContext(
            classification=sample_classification,
            correction_history=ctx,
        )
        prompt = build_feedback_prompt(fc)
        assert "succeeded" in prompt.lower()

    def test_max_retries_state_message(
        self, engine: StrategyEngine, sample_classification: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=sample_classification)
        for _ in range(6):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        fc = FeedbackContext(
            classification=sample_classification,
            correction_history=ctx,
        )
        prompt = build_feedback_prompt(fc)
        assert "paused" in prompt or "intervention" in prompt

    def test_user_input_included(
        self,
        engine: StrategyEngine,
        sample_test_result: TestResult,
        sample_classification: ClassificationResult,
    ) -> None:
        ctx = engine.initialize(classification=sample_classification)
        fc = FeedbackContext(
            test_results=sample_test_result,
            classification=sample_classification,
            correction_history=ctx,
            user_input="Try using a different algorithm.",
        )
        prompt = build_feedback_prompt(fc)
        assert "User Instructions" in prompt
        assert "Try using a different algorithm" in prompt


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_test_result(
        self, engine: StrategyEngine, sample_classification: ClassificationResult
    ) -> None:
        """TestResult with no failures."""
        tr = TestResult(total=0, passed=0, failed=0, errors=0)
        ctx = engine.initialize(classification=sample_classification)
        fc = FeedbackContext(
            test_results=tr,
            classification=sample_classification,
            correction_history=ctx,
        )
        prompt = build_feedback_prompt(fc)
        # Should not crash
        assert "No failure details available" in prompt

    def test_attempt_with_strategy_name(
        self, engine: StrategyEngine, sample_classification: ClassificationResult
    ) -> None:
        """Each attempt in history should show the strategy name."""
        ctx = engine.initialize(classification=sample_classification)
        ctx = engine.record_attempt(ctx, success=False, result="fail")
        fc = FeedbackContext(
            classification=sample_classification,
            correction_history=ctx,
        )
        prompt = build_feedback_prompt(fc)
        assert "compare_expected_actual" in prompt

    def test_prompt_contains_attempt_count(
        self, engine: StrategyEngine, sample_classification: ClassificationResult
    ) -> None:
        ctx = engine.initialize(classification=sample_classification)
        for _ in range(3):
            ctx = engine.record_attempt(ctx, success=False, result="fail")
        fc = FeedbackContext(
            classification=sample_classification,
            correction_history=ctx,
        )
        prompt = build_feedback_prompt(fc)
        assert "3" in prompt or "Attempt" in prompt