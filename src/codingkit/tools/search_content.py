"""search_content tool (PLAN T2.1)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from codingkit.tools.base import RiskLevel, Tool, ToolResult

_MAX_MATCHES = 1000


class SearchContentTool(Tool):
    name = "search_content"
    description = "Search file contents for a regex pattern and return matching lines."
    risk_level = RiskLevel.NORMAL

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regular expression to search for."},
                "path": {"type": "string", "description": "Directory or file to search. Defaults to '.'."},
            },
            "required": ["pattern"],
        }

    def execute(self, params: dict[str, Any]) -> ToolResult:
        pattern = params.get("pattern")
        path = params.get("path") or "."
        if not pattern:
            return ToolResult(success=False, output="", error="`pattern` is required")
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return ToolResult(success=False, output="", error=f"Invalid regex: {exc}")

        matches: list[dict[str, Any]] = []
        try:
            if os.path.isfile(path):
                files = [path]
            else:
                files = []
                for dirpath, _dirs, fnames in os.walk(path):
                    for fname in fnames:
                        files.append(os.path.join(dirpath, fname))
                        if len(files) >= _MAX_MATCHES:
                            break
                    if len(files) >= _MAX_MATCHES:
                        break

            for fpath in files:
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                        for lineno, line in enumerate(fh, start=1):
                            if regex.search(line):
                                matches.append({"file": fpath, "line": lineno, "text": line.rstrip("\n")})
                                if len(matches) >= _MAX_MATCHES:
                                    return ToolResult(success=True, output=json.dumps(matches, ensure_ascii=False))
                except OSError:
                    continue
        except OSError as exc:
            return ToolResult(success=False, output="", error=f"Search failed: {exc}")

        return ToolResult(success=True, output=json.dumps(matches, ensure_ascii=False))
