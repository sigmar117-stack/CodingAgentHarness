"""edit_file tool (PLAN T2.1)."""

from __future__ import annotations

from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace an exact string in a file with a new string."
    risk_level = RiskLevel.NORMAL

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to edit."},
                "old": {"type": "string", "description": "Exact text to find."},
                "new": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old", "new"],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        path = params.get("path")
        old = params.get("old")
        new = params.get("new")
        if not path or old is None or new is None:
            return ToolResult(success=False, output="", error="`path`, `old`, `new` are required")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except FileNotFoundError:
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        except OSError as exc:
            return ToolResult(success=False, output="", error=f"Could not read {path}: {exc}")

        count = content.count(old)
        if count == 0:
            return ToolResult(success=False, output="", error=f"`old` text not found in {path}")
        new_content = content.replace(old, new)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new_content)
        except OSError as exc:
            return ToolResult(success=False, output="", error=f"Could not write {path}: {exc}")
        return ToolResult(success=True, output=f"Replaced {count} occurrence(s) in {path}")
