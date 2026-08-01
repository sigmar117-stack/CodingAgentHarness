"""execute_command tool (PLAN T2.1) — DANGEROUS, not self-intercepting."""

from __future__ import annotations

import subprocess
from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult

_DEFAULT_TIMEOUT = 300  # SPEC §4.1 — shell command execution timeout


class ExecuteCommandTool(Tool):
    name = "execute_command"
    description = "Execute a shell command and return stdout/stderr/exit code."
    risk_level = RiskLevel.DANGEROUS

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 300)."},
            },
            "required": ["command"],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        command = params.get("command")
        if not command:
            return ToolResult(success=False, output="", error="`command` is required")
        timeout = params.get("timeout", _DEFAULT_TIMEOUT)
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error=f"Command timed out after {timeout}s")
        except OSError as exc:
            return ToolResult(success=False, output="", error=f"Could not execute command: {exc}")

        combined = f"[exit={proc.returncode}]\n{proc.stdout}"
        if proc.stderr:
            combined += f"\n[stderr]\n{proc.stderr}"
        return ToolResult(success=proc.returncode == 0, output=combined, error=None if proc.returncode == 0 else f"exit code {proc.returncode}")
