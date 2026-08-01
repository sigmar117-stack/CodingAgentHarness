"""Tool base classes (PLAN T2.1).

Every tool subclasses ``Tool``, declares a ``risk_level``, and implements
``execute(params) -> ToolResult``. Dangerous tools do **not** self-intercept —
that is the governance guardrail's job (PLAN T2.2 / SPEC §3.5). The registry
(T2.1) holds all tools and looks them up by name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

__all__ = ["RiskLevel", "ToolResult", "Tool"]


class RiskLevel(str, Enum):
    """Danger classification for a tool action."""

    NORMAL = "normal"
    DANGEROUS = "dangerous"


@dataclass
class ToolResult:
    """Result of a tool execution.

    ``output`` is always a string; structured tools (e.g. ``run_tests``)
    serialize structured data as JSON inside ``output``.
    """

    success: bool
    output: str
    error: Optional[str] = None


class Tool(ABC):
    """Abstract tool. Subclasses set ``name``, ``description``, ``risk_level``."""

    name: str = ""
    description: str = ""
    risk_level: RiskLevel = RiskLevel.NORMAL

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON-Schema describing the params this tool accepts (for the LLM)."""
        return {"type": "object", "properties": {}, "required": []}

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> ToolResult:
        """Run the tool with ``params`` and return a ``ToolResult``."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize tool metadata for LLM tool definitions / `codingkit tool list`."""
        return {
            "name": self.name,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "parameters": self.parameters,
        }
