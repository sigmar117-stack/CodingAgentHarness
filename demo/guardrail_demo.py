#!/usr/bin/env python3
"""Demo: Governance guardrail — dangerous command interception (T7.2).

Shows how the guardrail intercepts dangerous commands and allows safe ones.
No real LLM required — this is a deterministic demonstration.
"""

import sys
import os

# Ensure the package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from codingkit.core.llm_client import ToolCall
from codingkit.governance.guardrail import Guardrail, GuardrailResult


def print_result(action: ToolCall, result: GuardrailResult) -> None:
    status = "🚫 BLOCKED" if result.is_dangerous else "✅ ALLOWED"
    print(f"  Action: {action.name}({action.arguments})")
    print(f"  Result: {status}")
    if result.is_dangerous:
        print(f"  Reason: {result.risk_reason}")
    print()


def main() -> None:
    print("=" * 60)
    print("CodingKit — Governance Guardrail Demo")
    print("=" * 60)
    print()
    print("This demo shows how the guardrail intercepts dangerous actions")
    print("while allowing safe ones.")
    print()

    guardrail = Guardrail()

    # --- Test 1: Dangerous command (rm -rf) ---
    print("▶ Test 1: Dangerous command 'rm -rf /'")
    action = ToolCall(name="execute_command", arguments={"command": "rm -rf /"})
    result = guardrail.check(action)
    print_result(action, result)
    assert result.is_dangerous, "FAIL: rm -rf should be blocked!"

    # --- Test 2: Safe command ---
    print("▶ Test 2: Safe command 'ls -la'")
    action = ToolCall(name="execute_command", arguments={"command": "ls -la"})
    result = guardrail.check(action)
    print_result(action, result)
    assert not result.is_dangerous, "FAIL: ls should be allowed!"

    # --- Test 3: Dangerous tool (delete_file) ---
    print("▶ Test 3: Dangerous tool 'delete_file'")
    action = ToolCall(name="delete_file", arguments={"path": "/etc/passwd"})
    result = guardrail.check(action)
    print_result(action, result)
    assert result.is_dangerous, "FAIL: delete_file should be blocked!"

    # --- Test 4: Safe tool (read_file) ---
    print("▶ Test 4: Safe tool 'read_file'")
    action = ToolCall(name="read_file", arguments={"path": "README.md"})
    result = guardrail.check(action)
    print_result(action, result)
    assert not result.is_dangerous, "FAIL: read_file should be allowed!"

    # --- Test 5: Dangerous command with sudo ---
    print("▶ Test 5: Dangerous command with 'sudo'")
    action = ToolCall(name="execute_command", arguments={"command": "sudo apt-get install"})
    result = guardrail.check(action)
    print_result(action, result)
    assert result.is_dangerous, "FAIL: sudo should be blocked!"

    print("=" * 60)
    print("✅ All guardrail tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()