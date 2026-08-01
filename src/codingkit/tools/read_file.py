"""read_file tool (PLAN T2.1)."""

from __future__ import annotations

from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the text contents of a file at the given path."
    risk_level = RiskLevel.NORMAL

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to the file to read."}},
            "required": ["path"],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        path = params.get("path")
        if not path:
            return ToolResult(success=False, output="", error="`path` is required")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except FileNotFoundError:
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(success=False, output="", error=f"Could not read {path}: {exc}")
        return ToolResult(success=True, output=content)
