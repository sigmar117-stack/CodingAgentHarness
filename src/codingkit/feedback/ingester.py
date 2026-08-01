"""Feedback ingester — structures correction history into LLM context (PLAN T3.4).

The ingester takes a ``FeedbackContext`` (original code, test results,
classification, correction history, current strategy) and produces a
structured prompt that can be injected into the LLM conversation.

This bridges the deterministic feedback loop (validator → classifier →
strategy engine) and the LLM, ensuring the model always sees a complete,
well-organised picture of what has been tried and what should be tried next.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from codingkit.feedback.classifier import ClassificationResult
from codingkit.feedback.correction_state import (
    CorrectionAttempt,
    CorrectionContext,
    CorrectionState,
)
from codingkit.feedback.validator import TestResult


__all__ = [
    "FeedbackContext",
    "build_feedback_prompt",
    "MAX_HISTORY_ROUNDS",
]


#: Maximum number of correction-history rounds to include in the prompt.
#: When the history exceeds this, the oldest entries are truncated.
MAX_HISTORY_ROUNDS = 5


# ---------------------------------------------------------------------------
# FeedbackContext
# ---------------------------------------------------------------------------


@dataclass
class FeedbackContext:
    """All information needed to build a feedback prompt for the LLM.

    Attributes:
        original_code: The code snippet that was being tested (or a summary).
        test_results: The structured ``TestResult`` from the validator.
        classification: The ``ClassificationResult`` from the classifier.
        correction_history: The full ``CorrectionContext`` from the strategy
            engine, including the attempt history.
        current_strategy: The name of the strategy the LLM should try next
            (or ``None`` if the process has stopped).
        user_input: Optional additional instructions from the user.
    """

    __test__ = False  # prevent pytest from collecting this as a test class

    original_code: str = ""
    test_results: TestResult = field(default_factory=TestResult)
    classification: ClassificationResult = field(default_factory=ClassificationResult)
    correction_history: CorrectionContext = field(default_factory=CorrectionContext)
    current_strategy: Optional[str] = None
    user_input: str = ""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _format_test_result(tr: TestResult) -> str:
    """Format a ``TestResult`` into a readable summary block."""
    lines = [
        "## Test Results",
        "",
        f"- **Total**: {tr.total}",
        f"- **Passed**: {tr.passed}",
        f"- **Failed**: {tr.failed}",
        f"- **Errors**: {tr.errors}",
        "",
    ]

    if not tr.failures:
        lines.append("_No failure details available._")
    else:
        for i, fd in enumerate(tr.failures, 1):
            lines.append(f"### Failure {i}: `{fd.test_name}`")
            lines.append(f"- **Error type**: `{fd.error_type}`")
            lines.append(f"- **Message**: {fd.error_message}")
            # Include a short traceback snippet (first 5 lines)
            if fd.traceback:
                tb_lines = fd.traceback.strip().splitlines()
                snippet = "\n".join(tb_lines[:5])
                if len(tb_lines) > 5:
                    snippet += "\n  ..."
                lines.append(f"- **Traceback (snippet)**:\n```\n{snippet}\n```")
            lines.append("")

    return "\n".join(lines)


def _format_classification(cr: ClassificationResult) -> str:
    """Format a ``ClassificationResult`` into a readable block."""
    return (
        "## Failure Classification\n"
        "\n"
        f"- **Category**: `{cr.category.value}`\n"
        f"- **Confidence**: {cr.confidence:.2f}\n"
        f"- **Summary**: {cr.summary}\n"
        f"- **Key info**: {cr.key_info}\n"
    )


def _format_correction_history(ctx: CorrectionContext) -> str:
    """Format the correction attempt history.

    Truncates to the ``MAX_HISTORY_ROUNDS`` most recent attempts.
    """
    lines = [
        "## Correction History",
        "",
        f"- **Current state**: `{ctx.state.value}`",
        f"- **Attempt number**: {ctx.attempt_number}",
        f"- **Current strategy index**: {ctx.current_strategy_index}",
        f"- **Strategy chain**: {', '.join(ctx.strategy_chain)}",
        "",
    ]

    if not ctx.history:
        lines.append("_No correction attempts yet._\n")
    else:
        # Truncate to the most recent N rounds
        history = ctx.history[-MAX_HISTORY_ROUNDS:]
        if len(ctx.history) > MAX_HISTORY_ROUNDS:
            lines.append(
                f"_Showing the {MAX_HISTORY_ROUNDS} most recent of "
                f"{len(ctx.history)} total attempts._\n"
            )

        for i, attempt in enumerate(history, 1):
            status = "✅" if attempt.success else "❌"
            lines.append(
                f"### Attempt {i}: {status} `{attempt.strategy}`\n"
                f"- **Result**: {attempt.result}\n"
                f"- **Timestamp**: {attempt.timestamp.isoformat()}\n"
            )

    return "\n".join(lines)


def build_feedback_prompt(context: FeedbackContext) -> str:
    """Build a structured feedback prompt from the given context.

    The output is a Markdown document with sections for the original code,
    test results, classification, correction history, and the next strategy
    to try.  This is intended to be injected into the LLM message list as a
    ``user`` or ``assistant`` message.

    Args:
        context: All information about the current correction state.

    Returns:
        A structured Markdown string ready for LLM ingestion.
    """
    sections: list[str] = []

    # --- Header ---
    sections.append(
        "# CodingKit Feedback — Correction Context\n"
        "\n"
        "_This message is automatically generated by the feedback loop.  "
        "Use it to understand what went wrong and what to try next._\n"
    )

    # --- Original code ---
    if context.original_code:
        sections.append(
            "## Original Code\n"
            "\n"
            f"```\n{context.original_code}\n```\n"
        )

    # --- Test results ---
    sections.append(_format_test_result(context.test_results))

    # --- Classification ---
    sections.append(_format_classification(context.classification))

    # --- Correction history ---
    sections.append(_format_correction_history(context.correction_history))

    # --- Next strategy ---
    if context.current_strategy:
        sections.append(
            "## Next Strategy\n"
            "\n"
            f"The next strategy to try is: **`{context.current_strategy}`**\n"
        )
    elif context.correction_history.state == CorrectionState.SUCCEEDED:
        sections.append(
            "## Status\n"
            "\n"
            "_The correction process has succeeded — no further action needed._\n"
        )
    elif context.correction_history.state in (
        CorrectionState.MAX_RETRIES_REACHED,
        CorrectionState.STRATEGY_EXHAUSTED,
        CorrectionState.USER_INTERVENTION,
    ):
        sections.append(
            "## Status\n"
            "\n"
            "_The correction process has paused and requires user intervention.  "
            "Please review the history above and provide new instructions._\n"
        )

    # --- User input ---
    if context.user_input:
        sections.append(
            "## User Instructions\n"
            "\n"
            f"{context.user_input}\n"
        )

    return "\n\n---\n\n".join(sections)