"""git_operation tool (PLAN T2.1) — DANGEROUS, not self-intercepting.

Supports a small, common set of git operations (status / diff / log / add /
commit). Anything beyond these is rejected so the governance guardrail and
the user can always reason about what the agent asked git to do.
"""

from __future__ import annotations

import subprocess
from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult

_ALLOWED_OPERATIONS = {"status", "diff", "log", "add", "commit"}


class GitOperationTool(Tool):
    name = "git_operation"
    description = "Run a git operation: status, diff, log, add, or commit."
    risk_level = RiskLevel.DANGEROUS

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": sorted(_ALLOWED_OPERATIONS),
                    "description": "Git operation to perform.",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extra arguments (e.g. commit message via ['-m', 'msg']).",
                },
                "path": {"type": "string", "description": "Repository path. Defaults to '.'."},
            },
            "required": ["operation"],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        operation = params.get("operation")
        if not operation:
            return ToolResult(success=False, output="", error="`operation` is required")
        if operation not in _ALLOWED_OPERATIONS:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported git operation: {operation!r}. Allowed: {sorted(_ALLOWED_OPERATIONS)}",
            )
        args = params.get("args") or []
        if not isinstance(args, list):
            return ToolResult(success=False, output="", error="`args` must be a list of strings")
        path = params.get("path") or "."

        cmd = ["git", "-C", path, operation, *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error="git operation timed out")
        except (OSError, FileNotFoundError) as exc:
            return ToolResult(success=False, output="", error=f"Could not run git: {exc}")
        combined = proc.stdout
        if proc.stderr:
            combined += f"\n[stderr]\n{proc.stderr}"
        return ToolResult(
            success=proc.returncode == 0,
            output=combined.strip(),
            error=None if proc.returncode == 0 else f"git {operation} failed (exit {proc.returncode})",
        )
