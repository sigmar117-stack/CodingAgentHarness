"""delete_file tool (PLAN T2.1) — DANGEROUS, not self-intercepting."""

from __future__ import annotations

import os
import shutil
from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult


class DeleteFileTool(Tool):
    name = "delete_file"
    description = "Delete a file or directory at the given path."
    risk_level = RiskLevel.DANGEROUS

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to the file or directory to delete."}},
            "required": ["path"],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        path = params.get("path")
        if not path:
            return ToolResult(success=False, output="", error="`path` is required")
        if not os.path.exists(path):
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except OSError as exc:
            return ToolResult(success=False, output="", error=f"Could not delete {path}: {exc}")
        return ToolResult(success=True, output=f"Deleted {path}")
