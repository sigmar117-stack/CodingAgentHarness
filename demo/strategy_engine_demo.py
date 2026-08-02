#!/usr/bin/env python3
"""Demo: Strategy engine — multi-round strategy switching and escalation (T7.2).

Demonstrates the key state machine behaviors:
  1. 3 consecutive failures on the same strategy → auto-switch
  2. 6 total failures → MAX_RETRIES_REACHED escalation
  3. Strategy exhausted → STRATEGY_EXHAUSTED
  4. Success → SUCCEEDED
  5. Resume from paused state
No real LLM required — this is a deterministic demonstration.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Render emoji/box-drawing output on any console without crashing
# (Windows GBK consoles otherwise raise UnicodeEncodeError on 📌/✅).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from codingkit.feedback.classifier import ClassificationResult, FailureCategory
from codingkit.feedback.correction_state import CorrectionContext, CorrectionState
from codingkit.feedback.strategy_engine import StrategyEngine


def print_state(engine: StrategyEngine, ctx: CorrectionContext, label: str) -> None:
    summary = engine.status_summary(ctx)
    print(f"  [{label}]")
    print(f"    State: {summary['state']}")
    print(f"    Attempt: {summary['attempt_number']}")
    print(f"    Strategy index: {summary['current_strategy_index']}")
    print(f"    Current strategy: {summary['current_strategy']}")
    print(f"    Consecutive failures: {summary['consecutive_failures']}")
    print()


def main() -> None:
    print("=" * 60)
    print("CodingKit — Strategy Engine Deep Demo")
    print("=" * 60)
    print()
    print("This demo shows the strategy engine's state machine in detail,")
    print("covering auto-switching, escalation, success, and resume.")
    print()

    # =====================================================================
    # Demo 1: Auto-switch after 3 consecutive failures
    # =====================================================================
    print("─" * 60)
    print("📌 Demo 1: Auto-switch after 3 consecutive failures")
    print("─" * 60)
    print()

    engine = StrategyEngine()
    classification = ClassificationResult(
        category=FailureCategory.COMPILE_ERROR,
        confidence=1.0,
        summary="Compile error — SyntaxError: invalid syntax",
        key_info="SyntaxError: invalid syntax",
    )
    ctx = engine.initialize(classification=classification)
    print(f"  Strategy chain: {' → '.join(ctx.strategy_chain)}")
    print()

    for i in range(3):
        strategy = engine.next_strategy(ctx)
        print(f"  Attempt {i+1}: executing '{strategy}'")
        ctx = engine.record_attempt(ctx, success=False, result="Failed: syntax error persists")
        print_state(engine, ctx, f"After attempt {i+1}")

    assert ctx.current_strategy_index == 1, "FAIL: Should have switched to strategy 1"
    assert ctx.state == CorrectionState.ATTEMPTING
    print("  ✅ 3 consecutive failures → auto-switch to next strategy\n")

    # =====================================================================
    # Demo 2: 6 total failures → MAX_RETRIES_REACHED
    # =====================================================================
    print("─" * 60)
    print("📌 Demo 2: 6 total failures → MAX_RETRIES_REACHED")
    print("─" * 60)
    print()

    # Continue from demo 1 (already at index 1, 3 attempts)
    for i in range(3):
        strategy = engine.next_strategy(ctx)
        if strategy is None:
            print(f"  No strategy returned — state: {ctx.state.value}")
            break
        print(f"  Attempt {i+4}: executing '{strategy}'")
        ctx = engine.record_attempt(ctx, success=False, result="Failed: still broken")
        print_state(engine, ctx, f"After attempt {i+4}")

    assert ctx.state == CorrectionState.MAX_RETRIES_REACHED, \
        f"FAIL: Expected MAX_RETRIES_REACHED, got {ctx.state.value}"
    print("  ✅ 6 total failures → escalation to MAX_RETRIES_REACHED\n")

    # =====================================================================
    # Demo 3: Resume from MAX_RETRIES_REACHED
    # =====================================================================
    print("─" * 60)
    print("📌 Demo 3: Resume from MAX_RETRIES_REACHED")
    print("─" * 60)
    print()

    ctx = engine.resume(ctx)
    print(f"  After resume: state = {ctx.state.value}")
    print("  (The process can now continue with new strategies)")
    print()

    assert ctx.state == CorrectionState.ATTEMPTING
    print("  ✅ Resume sets state back to ATTEMPTING\n")

    # =====================================================================
    # Demo 4: Success → SUCCEEDED
    # =====================================================================
    print("─" * 60)
    print("📌 Demo 4: Success → SUCCEEDED")
    print("─" * 60)
    print()

    # Fresh start
    ctx = engine.initialize(classification=classification)
    strategy = engine.next_strategy(ctx)
    print(f"  Attempt 1: executing '{strategy}'")
    ctx = engine.record_attempt(ctx, success=True, result="Fixed the syntax error!")
    print_state(engine, ctx, "After success")

    assert ctx.state == CorrectionState.SUCCEEDED
    print("  ✅ Success → SUCCEEDED\n")

    # =====================================================================
    # Demo 5: Strategy exhausted (custom short chain)
    # =====================================================================
    print("─" * 60)
    print("📌 Demo 5: Strategy exhausted (short chain)")
    print("─" * 60)
    print()

    ctx = engine.initialize(
        classification=classification,
        custom_strategy_chain=["quick_fix", "escalate_to_user"],
    )
    print(f"  Custom chain: {' → '.join(ctx.strategy_chain)}")
    print()

    for i in range(3):
        strategy = engine.next_strategy(ctx)
        if strategy is None:
            print(f"  No strategy — state: {ctx.state.value}")
            break
        print(f"  Attempt {i+1}: executing '{strategy}'")
        ctx = engine.record_attempt(ctx, success=False, result="Failed")
        print_state(engine, ctx, f"After attempt {i+1}")

    # Check if next_strategy detects escalate_to_user
    remaining = engine.next_strategy(ctx)
    if remaining is None:
        print(f"  (next_strategy confirms: state={ctx.state.value})")
    else:
        print(f"  (next_strategy returned: {remaining})")

    assert ctx.state == CorrectionState.STRATEGY_EXHAUSTED or \
           ctx.state == CorrectionState.USER_INTERVENTION, \
           f"FAIL: Expected terminal state, got {ctx.state.value}"
    print("  ✅ Short chain exhausted → terminal state\n")

    # =====================================================================
    # Summary
    # =====================================================================
    print("=" * 60)
    print("✅ All strategy engine demos passed!")
    print("=" * 60)
    print()
    print("Demonstrated behaviors:")
    print("  1. Auto-switch after 3 consecutive failures on same strategy")
    print("  2. Escalation after 6 total failures (MAX_RETRIES_REACHED)")
    print("  3. Resume from paused state (ATTEMPTING)")
    print("  4. Success detection (SUCCEEDED)")
    print("  5. Strategy exhaustion (STRATEGY_EXHAUSTED)")
    print()


if __name__ == "__main__":
    main()