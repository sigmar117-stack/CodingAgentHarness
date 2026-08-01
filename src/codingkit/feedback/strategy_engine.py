"""Correction strategy engine — state machine (PLAN T3.3, main focus).

This module implements the correction state machine that:

* Maps a ``FailureCategory`` to a strategy chain (ordered list of strategies).
* Manages state transitions: attempting → succeeded / exhausted / max-retries.
* Tracks consecutive failures per strategy (auto-switch after 3).
* Tracks total failures (escalate after 6).
* Supports ``resume()`` to continue from a saved ``CorrectionContext``.

Strategy chains per failure category (SPEC §3.3.3):
===================================================

| Category           | Strategy chain                                      |
|-------------------|-----------------------------------------------------|
| COMPILE_ERROR     | check_syntax → check_code_structure → escalate      |
| ASSERTION_ERROR   | compare_expected_actual → check_logic → escalate    |
| TIMEOUT           | optimize_algorithm → reduce_iterations → escalate   |
| ENVIRONMENT_ERROR | auto_install_deps → check_dependency_decl → escalate|
| TYPE_ERROR        | check_type_annotations → check_type_conversion → escalate |
| IMPORT_ERROR      | check_import_path → confirm_filename → escalate     |
| BOUNDARY_ERROR    | check_boundary_conditions → check_null_handling → escalate |
| INFINITE_LOOP     | check_termination_condition → optimize_recursion → escalate |
| UNCLASSIFIED      | general_correction → escalate                      |
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from codingkit.feedback.classifier import (
    ClassificationResult,
    FailureCategory,
)
from codingkit.feedback.correction_state import (
    CorrectionAttempt,
    CorrectionContext,
    CorrectionState,
)


__all__ = [
    "StrategyEngine",
    "STRATEGY_CHAINS",
    "get_strategy_chain",
]


# ---------------------------------------------------------------------------
# Strategy chains — per failure category (SPEC §3.3.3)
# ---------------------------------------------------------------------------

#: Default strategy chain for each failure category.
#: The last entry in every chain is always "escalate_to_user" (handled by the
#: state machine as ``STRATEGY_EXHAUSTED`` / ``USER_INTERVENTION``).
STRATEGY_CHAINS: dict[FailureCategory, list[str]] = {
    FailureCategory.COMPILE_ERROR: [
        "check_syntax",
        "check_code_structure",
        "escalate_to_user",
    ],
    FailureCategory.ASSERTION_ERROR: [
        "compare_expected_actual",
        "check_logic",
        "escalate_to_user",
    ],
    FailureCategory.TIMEOUT: [
        "optimize_algorithm",
        "reduce_iterations",
        "escalate_to_user",
    ],
    FailureCategory.ENVIRONMENT_ERROR: [
        "auto_install_deps",
        "check_dependency_declaration",
        "escalate_to_user",
    ],
    FailureCategory.TYPE_ERROR: [
        "check_type_annotations",
        "check_type_conversion",
        "escalate_to_user",
    ],
    FailureCategory.IMPORT_ERROR: [
        "check_import_path",
        "confirm_filename",
        "escalate_to_user",
    ],
    FailureCategory.BOUNDARY_ERROR: [
        "check_boundary_conditions",
        "check_null_handling",
        "escalate_to_user",
    ],
    FailureCategory.INFINITE_LOOP: [
        "check_termination_condition",
        "optimize_recursion",
        "escalate_to_user",
    ],
    FailureCategory.UNCLASSIFIED: [
        "general_correction",
        "escalate_to_user",
    ],
}

#: Maximum consecutive failures allowed for a single strategy before auto-switch.
_MAX_CONSECUTIVE_FAILURES = 3

#: Maximum total attempts before escalating to user.
_MAX_TOTAL_ATTEMPTS = 6


def get_strategy_chain(category: FailureCategory) -> list[str]:
    """Return the strategy chain for a given failure category.

    Args:
        category: The failure category to look up.

    Returns:
        A list of strategy names (ordered). If the category is not recognised,
        returns the ``UNCLASSIFIED`` chain.
    """
    return STRATEGY_CHAINS.get(category, STRATEGY_CHAINS[FailureCategory.UNCLASSIFIED])


# ---------------------------------------------------------------------------
# StrategyEngine
# ---------------------------------------------------------------------------


class StrategyEngine:
    """State machine for correction strategy management.

    Usage::

        engine = StrategyEngine()
        ctx = engine.initialize(
            session_id="sess-1",
            classification=ClassificationResult(...),
        )
        # Loop:
        if engine.can_continue(ctx):
            strategy = engine.next_strategy(ctx)
            # ... apply strategy, record result ...
            ctx = engine.record_attempt(ctx, success=False, result="...")
        # Check final state:
        print(ctx.state)
    """

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(
        self,
        session_id: str = "",
        turn_id: str = "",
        classification: ClassificationResult | None = None,
        custom_strategy_chain: list[str] | None = None,
    ) -> CorrectionContext:
        """Create a new ``CorrectionContext`` and set its strategy chain.

        Args:
            session_id: Optional session identifier.
            turn_id: Optional turn identifier.
            classification: The classification result from the classifier.
            custom_strategy_chain: If provided, use this chain instead of
                the default one for the classification's category.

        Returns:
            A fresh ``CorrectionContext`` in ``ATTEMPTING`` state.
        """
        cat = (
            classification.category
            if classification is not None
            else FailureCategory.UNCLASSIFIED
        )
        chain = (
            list(custom_strategy_chain)
            if custom_strategy_chain is not None
            else get_strategy_chain(cat)
        )

        return CorrectionContext(
            session_id=session_id,
            turn_id=turn_id,
            attempt_number=0,
            current_strategy_index=0,
            strategy_chain=chain,
            history=[],
            classification=classification or ClassificationResult(),
            state=CorrectionState.ATTEMPTING,
            consecutive_failures=0,
        )

    # ------------------------------------------------------------------
    # Core state-machine logic
    # ------------------------------------------------------------------

    def next_strategy(self, context: CorrectionContext) -> str | None:
        """Return the next strategy to try, or ``None`` if the process should stop.

        This method checks stopping conditions before returning a strategy:

        * If total attempts >= 6 → sets ``MAX_RETRIES_REACHED``, returns ``None``.
        * If current strategy index is past the end of the chain →
          sets ``STRATEGY_EXHAUSTED``, returns ``None``.
        * If the chain has an ``escalate_to_user`` entry at the current index →
          sets ``USER_INTERVENTION``, returns ``None``.
        * Otherwise returns the strategy name at the current index.

        Args:
            context: The current correction context (mutated in place).

        Returns:
            The strategy name to try, or ``None`` if the process should stop.
        """
        # --- Check total-attempts ceiling ---
        if context.attempt_number >= _MAX_TOTAL_ATTEMPTS:
            context.state = CorrectionState.MAX_RETRIES_REACHED
            return None

        # --- Check index bounds ---
        if context.current_strategy_index >= len(context.strategy_chain):
            context.state = CorrectionState.STRATEGY_EXHAUSTED
            return None

        strategy = context.strategy_chain[context.current_strategy_index]

        # --- Check for escalate_to_user ---
        if strategy == "escalate_to_user":
            context.state = CorrectionState.USER_INTERVENTION
            return None

        return strategy

    def record_attempt(
        self,
        context: CorrectionContext,
        success: bool,
        result: str = "",
    ) -> CorrectionContext:
        """Record the outcome of a correction attempt and update state.

        If the attempt was successful, the context transitions to ``SUCCEEDED``.
        If it failed, the consecutive-failure counter increments, and the
        strategy may be switched if the counter exceeds the threshold.

        Args:
            context: The current correction context (mutated in place).
            success: Whether the attempt succeeded.
            result: A description of the attempt's outcome.

        Returns:
            The same ``CorrectionContext`` (mutated) for chaining.
        """
        context.attempt_number += 1

        attempt = CorrectionAttempt(
            strategy=context.strategy_chain[context.current_strategy_index]
            if context.current_strategy_index < len(context.strategy_chain)
            else "unknown",
            result=result,
            success=success,
            timestamp=datetime.now(timezone.utc),
        )
        context.history.append(attempt)

        if success:
            context.state = CorrectionState.SUCCEEDED
            return context

        # --- Failure handling ---
        context.consecutive_failures += 1

        # Same strategy failed 3+ times → switch to next strategy
        if context.consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
            context.current_strategy_index += 1
            context.consecutive_failures = 0

        # Re-check stopping conditions (total attempts, index bounds)
        if context.attempt_number >= _MAX_TOTAL_ATTEMPTS:
            context.state = CorrectionState.MAX_RETRIES_REACHED
        elif context.current_strategy_index >= len(context.strategy_chain):
            context.state = CorrectionState.STRATEGY_EXHAUSTED
        # else: still ATTEMPTING

        return context

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def can_continue(self, context: CorrectionContext) -> bool:
        """Check whether the correction process can continue.

        Returns ``True`` when the context is in ``ATTEMPTING`` state and there
        are strategies remaining.
        """
        return (
            context.state == CorrectionState.ATTEMPTING
            and context.current_strategy_index < len(context.strategy_chain)
            and context.attempt_number < _MAX_TOTAL_ATTEMPTS
        )

    def resume(self, context: CorrectionContext) -> CorrectionContext:
        """Resume a previously saved context.

        If the context is in a terminal state (SUCCEEDED, CANCELLED), it is
        returned unchanged.  If in a paused state (USER_INTERVENTION,
        STRATEGY_EXHAUSTED, MAX_RETRIES_REACHED), the state is reset to
        ATTEMPTING so the caller can inject new strategies or continue.

        Args:
            context: The saved context to resume from.

        Returns:
            The context with state reset to ATTEMPTING if it was paused.
        """
        if context.state in (CorrectionState.SUCCEEDED, CorrectionState.CANCELLED):
            return context  # terminal — cannot resume

        if context.state in (
            CorrectionState.USER_INTERVENTION,
            CorrectionState.STRATEGY_EXHAUSTED,
            CorrectionState.MAX_RETRIES_REACHED,
        ):
            # Reset to ATTEMPTING so the caller can continue.
            context.state = CorrectionState.ATTEMPTING

        return context

    def cancel(self, context: CorrectionContext) -> CorrectionContext:
        """Cancel the correction process.

        Sets the state to ``CANCELLED``.
        """
        context.state = CorrectionState.CANCELLED
        return context

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def status_summary(self, context: CorrectionContext) -> dict:
        """Return a human-readable summary of the current correction state.

        This is useful for logging and WebUI display.
        """
        return {
            "state": context.state.value,
            "attempt_number": context.attempt_number,
            "current_strategy_index": context.current_strategy_index,
            "current_strategy": (
                context.strategy_chain[context.current_strategy_index]
                if context.current_strategy_index < len(context.strategy_chain)
                else None
            ),
            "strategy_chain": list(context.strategy_chain),
            "consecutive_failures": context.consecutive_failures,
            "total_attempts": context.attempt_number,
            "max_total_attempts": _MAX_TOTAL_ATTEMPTS,
            "max_consecutive_failures": _MAX_CONSECUTIVE_FAILURES,
            "classification": {
                "category": context.classification.category.value,
                "confidence": context.classification.confidence,
                "summary": context.classification.summary,
            },
            "history": [
                {
                    "strategy": h.strategy,
                    "success": h.success,
                    "result": h.result,
                    "timestamp": h.timestamp.isoformat(),
                }
                for h in context.history
            ],
        }