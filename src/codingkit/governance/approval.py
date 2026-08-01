"""HITL approval state machine (PLAN T2.2).

The ``ApprovalHandler`` implements a human-in-the-loop (HITL) approval flow
for dangerous actions.  It presents the action to the user, accepts one of
three decisions, and returns the result.

Two modes are supported:

**CLI mode** (default) — prompts on the terminal via ``input()``::

    Prompt: "Approve this action? [y]es / [n]o / [m]odify"
        y / yes  → APPROVED
        n / no   → REJECTED
        m        → MODIFIED (prompts for new command string)
        <empty>  → REJECTED
        <other>  → retry prompt
        <timeout>→ REJECTED (auto-deny)

**Remote mode** — used by the WebUI.  A callback is set via
``set_remote_handler()`` and the handler waits on a ``threading.Event``
for the frontend to submit its decision via ``set_remote_decision()``.
"""

from __future__ import annotations

import sys
import threading
from datetime import timedelta
from enum import Enum
from typing import Any, Callable, Optional, Tuple

from codingkit.core.llm_client import ToolCall

__all__ = ["ApprovalDecision", "ApprovalHandler"]


# ---------------------------------------------------------------------------
# ApprovalDecision enum
# ---------------------------------------------------------------------------


class ApprovalDecision(str, Enum):
    """Outcome of a human approval request."""

    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


# ---------------------------------------------------------------------------
# ApprovalHandler
# ---------------------------------------------------------------------------


class ApprovalHandler:
    """Human-in-the-loop approval state machine.

    Supports two modes:

    * **CLI mode** (default): prompts on the terminal via ``input()``.
    * **Remote mode**: call ``set_remote_handler(callback)`` to push
      approval requests to a WebUI, then call ``set_remote_decision()``
      from the REST endpoint.

    Args:
        timeout: Maximum time to wait for user input before auto-denying.
            Defaults to 120 seconds.
    """

    def __init__(self, timeout: timedelta = timedelta(seconds=120)) -> None:
        self._timeout = timeout
        self._remote_callback: Optional[Callable[[ToolCall], None]] = None
        self._decision_event = threading.Event()
        self._decision: Tuple[ApprovalDecision, Optional[dict[str, Any]]] = (
            ApprovalDecision.REJECTED,
            None,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def request_approval(
        self, action: ToolCall
    ) -> Tuple[ApprovalDecision, Optional[dict[str, Any]]]:
        """Present *action* to the user and return the decision.

        If a remote callback is set, the request is pushed asynchronously
        and this method blocks until ``set_remote_decision()`` is called
        or the timeout expires.

        Returns:
            A tuple of ``(ApprovalDecision, modified_params)``.
            ``modified_params`` is ``None`` unless the decision is ``MODIFIED``.
        """
        if self._remote_callback is not None:
            return self._request_remote(action)

        self._display_action(action)
        decision, modified_params = self._read_with_timeout(action)

        if decision == ApprovalDecision.MODIFIED and modified_params is not None:
            return decision, modified_params

        return decision, None

    def set_remote_handler(
        self, callback: Callable[[ToolCall], None]
    ) -> None:
        """Enable remote approval mode.

        When set, ``request_approval()`` will call *callback* with the
        action and then block until ``set_remote_decision()`` is called.

        Set *callback* to ``None`` to revert to CLI mode.
        """
        self._remote_callback = callback

    def set_remote_decision(
        self,
        decision: ApprovalDecision,
        modified_params: Optional[dict[str, Any]] = None,
    ) -> None:
        """Submit a remote decision (called from a REST endpoint)."""
        self._decision = (decision, modified_params)
        self._decision_event.set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request_remote(
        self, action: ToolCall
    ) -> Tuple[ApprovalDecision, Optional[dict[str, Any]]]:
        """Push the approval request via the remote callback and wait for a decision."""
        self._decision_event.clear()
        if self._remote_callback:
            self._remote_callback(action)

        # Wait for the decision with a timeout
        timeout_sec = self._timeout.total_seconds()
        if timeout_sec > 0:
            self._decision_event.wait(timeout_sec)

        if not self._decision_event.is_set():
            # Timeout — auto-deny
            return ApprovalDecision.REJECTED, None

        return self._decision

    def _display_action(self, action: ToolCall) -> None:
        """Print a human-readable description of the action."""
        print(f"\n{'=' * 60}", file=sys.stderr)
        print("  DANGEROUS ACTION DETECTED", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
        print(f"  Tool   : {action.name}", file=sys.stderr)
        for key, value in action.arguments.items():
            print(f"  {key:8s}: {value}", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)

    def _read_with_timeout(
        self, action: ToolCall
    ) -> Tuple[ApprovalDecision, Optional[dict[str, Any]]]:
        """Read user input with a deadline.  On timeout, auto-deny.

        Uses a daemon thread for cross-platform compatibility (Windows does
        not support ``signal.SIGALRM``).

        Returns ``(REJECTED, None)`` on timeout.
        """
        timeout_sec = self._timeout.total_seconds()

        # If timeout is zero or negative, deny immediately.
        if timeout_sec <= 0:
            print("\n  [TIMEOUT] Auto-denied (timeout <= 0).", file=sys.stderr)
            return ApprovalDecision.REJECTED, None

        result: list[Tuple[ApprovalDecision, Optional[dict[str, Any]]]] = []

        def _target() -> None:
            result.append(self._prompt_loop(action))

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(timeout_sec)

        if thread.is_alive():
            # Thread is still running → timed out.
            print("\n  [TIMEOUT] Auto-denied.", file=sys.stderr)
            return ApprovalDecision.REJECTED, None

        if not result:
            return ApprovalDecision.REJECTED, None

        return result[0]

    def _prompt_loop(
        self, action: ToolCall
    ) -> Tuple[ApprovalDecision, Optional[dict[str, Any]]]:
        """Repeatedly prompt until a valid decision is entered."""
        while True:
            user_input = input("  Approve? [y]es / [n]o / [m]odify: ").strip().lower()

            if user_input in ("y", "yes"):
                return ApprovalDecision.APPROVED, None
            if user_input in ("n", "no", ""):
                return ApprovalDecision.REJECTED, None
            if user_input == "m":
                return self._handle_modify(action)

            print(f"  Invalid input '{user_input}'.  Enter y, n, or m.", file=sys.stderr)

    def _handle_modify(
        self, action: ToolCall
    ) -> Tuple[ApprovalDecision, Optional[dict[str, Any]]]:
        """Handle the 'modify' path: prompt for a new command and return MODIFIED."""
        new_command = input("  Enter modified command: ").strip()
        modified_params = dict(action.arguments)

        # For execute_command, the primary param to modify is "command".
        if "command" in modified_params:
            modified_params["command"] = new_command
        else:
            # For other tools, store the full modified input under a key.
            modified_params["_modified_input"] = new_command

        return ApprovalDecision.MODIFIED, modified_params