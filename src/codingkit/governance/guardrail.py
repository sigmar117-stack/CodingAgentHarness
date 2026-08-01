"""Governance guardrail — dangerous-action detection (PLAN T2.2).

The ``Guardrail`` class checks a ``ToolCall`` against two rule sets:

1. **Dangerous tool names** — the four tools marked ``DANGEROUS`` in the
   tool registry always trigger a guardrail check.
2. **Dangerous command patterns** — for ``execute_command``, the command
   string is scanned for known destructive patterns (``rm -rf``, ``sudo``,
   ``dd``, ``mkfs``, etc.).

The result is a ``GuardrailResult`` with a boolean flag, a human-readable
reason, and an optional safe alternative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from codingkit.core.llm_client import ToolCall

__all__ = ["GuardrailResult", "Guardrail"]

# ---------------------------------------------------------------------------
# Public data class
# ---------------------------------------------------------------------------


@dataclass
class GuardrailResult:
    """Outcome of a guardrail check.

    Attributes:
        is_dangerous: Whether the action is considered dangerous.
        risk_reason: Human-readable explanation (empty if safe).
        suggested_safe_alternative: Optional safe alternative suggestion.
    """

    is_dangerous: bool = False
    risk_reason: str = ""
    suggested_safe_alternative: Optional[str] = None


# ---------------------------------------------------------------------------
# Dangerous-tool name list
# ---------------------------------------------------------------------------

_DANGEROUS_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "execute_command",
        "delete_file",
        "install_dependencies",
        "git_operation",
    }
)

# ---------------------------------------------------------------------------
# Dangerous command patterns (for execute_command)
# ---------------------------------------------------------------------------

# Compiled regex patterns checked against the command string.
_DANGEROUS_COMMAND_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+-rf\b", re.IGNORECASE), "Recursive force-delete (rm -rf)"),
    (re.compile(r"\bsudo\b", re.IGNORECASE), "Privilege escalation (sudo)"),
    (re.compile(r"\bdd\b", re.IGNORECASE), "Raw disk write (dd)"),
    (re.compile(r"\bmkfs\b", re.IGNORECASE), "Filesystem creation (mkfs)"),
    (re.compile(r"\bchmod\s+-R\s+777\b", re.IGNORECASE), "Overly permissive recursive chmod"),
    (re.compile(r"\b>:?\s*/dev/", re.IGNORECASE), "Direct device write"),
    (re.compile(r"\bwget\s+|curl\s+.*\||curl\s+.*\bbash\b", re.IGNORECASE), "Remote script pipe-to-shell"),
    (re.compile(r"\bpasswd\b", re.IGNORECASE), "Password operation"),
    (re.compile(r"\bkillall\b|\bpkill\b", re.IGNORECASE), "Process kill-all"),
    (re.compile(r"\bshutdown\b|\breboot\b|\bpoweroff\b|\bhalt\b", re.IGNORECASE), "System shutdown / reboot"),
]


# ---------------------------------------------------------------------------
# Guardrail
# ---------------------------------------------------------------------------


class Guardrail:
    """Checks a ``ToolCall`` against dangerous-action rules.

    Usage::

        guardrail = Guardrail()
        result = guardrail.check(tool_call)
        if result.is_dangerous:
            # route to ApprovalHandler
    """

    def check(self, action: ToolCall) -> GuardrailResult:
        """Evaluate *action* and return a ``GuardrailResult``.

        The check proceeds in two stages:

        1. **Tool name check** — if the tool is in the dangerous-name list,
           mark it as dangerous immediately.
        2. **Command-pattern check** — for ``execute_command``, scan the
           ``command`` argument against known destructive patterns.
        """
        # --- Stage 1: dangerous tool name ---
        if action.name in _DANGEROUS_TOOL_NAMES and action.name != "execute_command":
            return GuardrailResult(
                is_dangerous=True,
                risk_reason=f"Dangerous tool: {action.name}",
            )

        # --- Stage 2: dangerous command pattern (execute_command only) ---
        if action.name == "execute_command":
            command = action.arguments.get("command", "")
            if not isinstance(command, str):
                command = str(command)
            for pattern, reason in _DANGEROUS_COMMAND_PATTERNS:
                if pattern.search(command):
                    return GuardrailResult(
                        is_dangerous=True,
                        risk_reason=f"Dangerous command pattern detected: {reason}",
                    )

        # --- Safe ---
        return GuardrailResult(is_dangerous=False, risk_reason="")