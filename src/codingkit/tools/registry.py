"""Tool registry (PLAN T2.1).

Holds all 10 tools and looks them up by name. ``get(name)`` returns ``None``
for unknown names so the dispatcher can fall through to a friendly error.
"""

from __future__ import annotations

from typing import Optional

from codingkit.tools.base import Tool
from codingkit.tools.delete_file import DeleteFileTool
from codingkit.tools.edit_file import EditFileTool
from codingkit.tools.execute_command import ExecuteCommandTool
from codingkit.tools.git_operation import GitOperationTool
from codingkit.tools.install_dependencies import InstallDependenciesTool
from codingkit.tools.read_file import ReadFileTool
from codingkit.tools.run_tests import RunTestsTool
from codingkit.tools.search_content import SearchContentTool
from codingkit.tools.search_files import SearchFilesTool
from codingkit.tools.write_file import WriteFileTool

__all__ = ["ToolRegistry", "default_registry", "ALL_TOOLS"]

ALL_TOOLS: list[Tool] = [
    ReadFileTool(),
    WriteFileTool(),
    EditFileTool(),
    ExecuteCommandTool(),
    RunTestsTool(),
    SearchFilesTool(),
    SearchContentTool(),
    InstallDependenciesTool(),
    DeleteFileTool(),
    GitOperationTool(),
]


class ToolRegistry:
    """In-memory registry of available tools.

    Tools can be *disabled* by name (``disable``) and re-enabled
    (``enable``).  A disabled tool is still present in the registry (so the
    agent can report a clear "tool disabled" error rather than "unknown
    tool") but is omitted from the LLM's tool definitions and refused at
    execution time — this is what makes ``codingkit tool enable/disable``
    actually take effect rather than being an echo.
    """

    def __init__(self, tools: Optional[list[Tool]] = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._disabled: set[str] = set()
        for tool in tools or ALL_TOOLS:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Return the tool with ``name``, or ``None`` if not registered."""
        return self._tools.get(name)

    def disable(self, name: str) -> bool:
        """Disable *name*.  Returns ``True`` if the tool exists (now disabled)."""
        if name not in self._tools:
            return False
        self._disabled.add(name)
        return True

    def enable(self, name: str) -> bool:
        """Re-enable *name*.  Returns ``True`` if the tool exists."""
        if name not in self._tools:
            return False
        self._disabled.discard(name)
        return True

    def is_disabled(self, name: str) -> bool:
        """Return ``True`` iff *name* is a registered but disabled tool."""
        return name in self._disabled

    def disabled_names(self) -> list[str]:
        """Sorted list of disabled tool names."""
        return sorted(self._disabled)

    def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def dangerous_tools(self) -> list[Tool]:
        from codingkit.tools.base import RiskLevel

        return [t for t in self._tools.values() if t.risk_level == RiskLevel.DANGEROUS]


def default_registry() -> ToolRegistry:
    """A fresh registry pre-populated with the 10 built-in tools."""
    return ToolRegistry()
