#!/usr/bin/env python3
"""Demo: Feedback loop — classification + strategy engine (T7.2).

Constructs a test failure, classifies it, then runs through the strategy
engine to show the state machine in action.
No real LLM required — this is a deterministic demonstration.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Render emoji/box-drawing output on any console without crashing
# (Windows GBK consoles otherwise raise UnicodeEncodeError on ✅/▶).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from codingkit.feedback.classifier import (
    FailureCategory,
    classify,
)
from codingkit.feedback.correction_state import CorrectionState
from codingkit.feedback.strategy_engine import (
    StrategyEngine,
    get_strategy_chain,
)
from codingkit.feedback.validator import FailureDetail, TestResult


def main() -> None:
    print("=" * 60)
    print("CodingKit — Feedback Loop Demo")
    print("=" * 60)
    print()

    # --- Step 1: Create a test failure ---
    print("▶ Step 1: Create a test failure (AssertionError)")
    failure = FailureDetail(
        test_name="test_math::test_add",
        error_type="AssertionError",
        error_message="expected 5, got 4",
        traceback="E       AssertionError: expected 5, got 4\n"
        "test_math.py:12: in test_add\n"
        "    assert add(2, 2) == 5",
    )
    test_result = TestResult(
        total=5,
        passed=3,
        failed=1,
        errors=1,
        failures=[failure],
        raw_output="FAILED test_math.py::test_add - AssertionError: expected 5, got 4",
    )
    print(f"  Test: {failure.test_name}")
    print(f"  Error: {failure.error_type}: {failure.error_message}")
    print()

    # --- Step 2: Classify the failure ---
    print("▶ Step 2: Classify the failure")
    classification = classify(test_result)[0]
    print(f"  Category: {classification.category.value}")
    print(f"  Confidence: {classification.confidence:.2f}")
    print(f"  Summary: {classification.summary}")
    assert classification.category == FailureCategory.ASSERTION_ERROR
    print()

    # --- Step 3: Show strategy chain ---
    print("▶ Step 3: Strategy chain for this failure type")
    chain = get_strategy_chain(classification.category)
    print(f"  Strategies: {' → '.join(chain)}")
    print()

    # --- Step 4: Run the strategy engine ---
    print("▶ Step 4: Run the strategy engine")
    engine = StrategyEngine()
    ctx = engine.initialize(classification=classification)
    print(f"  Initial state: {ctx.state.value}")
    print(f"  Strategy chain: {', '.join(ctx.strategy_chain)}")
    print()

    # --- Step 5: Simulate attempts ---
    print("▶ Step 5: Simulate correction attempts")
    for i in range(3):
        strategy = engine.next_strategy(ctx)
        if strategy is None:
            print(f"  Attempt {i+1}: No strategy (state={ctx.state.value})")
            break
        print(f"  Attempt {i+1}: Strategy = '{strategy}'")
        ctx = engine.record_attempt(ctx, success=False, result=f"Failed attempt {i+1}")
        print(f"    → State: {ctx.state.value}, "
              f"consecutive_failures: {ctx.consecutive_failures}, "
              f"index: {ctx.current_strategy_index}")
        print()

    # --- Step 6: Check final state ---
    print("▶ Step 6: Final state")
    summary = engine.status_summary(ctx)
    print(f"  State: {summary['state']}")
    print(f"  Total attempts: {summary['attempt_number']}")
    print(f"  Current strategy index: {summary['current_strategy_index']}")
    print(f"  History entries: {len(summary['history'])}")
    print()

    assert ctx.state == CorrectionState.ATTEMPTING
    assert ctx.current_strategy_index == 1  # Switched after 3 consecutive failures
    print("=" * 60)
    print("✅ Feedback loop demo passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()