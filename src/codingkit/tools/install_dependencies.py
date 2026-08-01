"""install_dependencies tool (PLAN T2.1) — DANGEROUS, not self-intercepting."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult


class InstallDependenciesTool(Tool):
    name = "install_dependencies"
    description = "Install Python packages via pip."
    risk_level = RiskLevel.DANGEROUS

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Package names (with optional version specifiers).",
                }
            },
            "required": ["packages"],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        packages = params.get("packages")
        if not packages or not isinstance(packages, list):
            return ToolResult(success=False, output="", error="`packages` (list[str]) is required")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", *packages],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error="pip install timed out")
        except OSError as exc:
            return ToolResult(success=False, output="", error=f"Could not run pip: {exc}")
        return ToolResult(
            success=proc.returncode == 0,
            output=proc.stdout,
            error=None if proc.returncode == 0 else (proc.stderr or "pip install failed"),
        )
