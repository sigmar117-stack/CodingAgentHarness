"""search_files tool (PLAN T2.1)."""

from __future__ import annotations

import glob
import json
import os
from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Find files matching a glob pattern under a path."
    risk_level = RiskLevel.NORMAL

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.py'."},
                "path": {"type": "string", "description": "Directory to search in. Defaults to '.'."},
            },
            "required": ["pattern"],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        pattern = params.get("pattern")
        path = params.get("path") or "."
        if not pattern:
            return ToolResult(success=False, output="", error="`pattern` is required")
        full = os.path.join(path, pattern)
        try:
            matches = sorted(glob.glob(full, recursive=True))
        except (OSError, ValueError) as exc:
            return ToolResult(success=False, output="", error=f"Search failed: {exc}")
        return ToolResult(success=True, output=json.dumps(matches, ensure_ascii=False))
