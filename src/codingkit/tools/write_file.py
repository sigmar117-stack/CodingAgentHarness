"""write_file tool (PLAN T2.1)."""

from __future__ import annotations

from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write text content to a file, creating or overwriting it."
    risk_level = RiskLevel.NORMAL

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to write."},
                "content": {"type": "string", "description": "Content to write."},
            },
            "required": ["path", "content"],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        path = params.get("path")
        content = params.get("content")
        if not path or content is None:
            return ToolResult(success=False, output="", error="`path` and `content` are required")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as exc:
            return ToolResult(success=False, output="", error=f"Could not write {path}: {exc}")
        return ToolResult(success=True, output=f"Wrote {len(content)} chars to {path}")
