"""Context builder — assembles LLM messages from task, tools, and history (PLAN T4.1).

The ``ContextBuilder`` collects:

* A system prompt describing the agent's role and available tools.
* The user's task description.
* Relevant memories from past sessions.
* The current session's turn history.
* Any active feedback-loop context (correction history, test results).

It produces a ``list[dict]`` of messages ready to pass to ``LLMClient.generate()``
in the CodingKit unified message format.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from codingkit.feedback.ingester import FeedbackContext, build_feedback_prompt
from codingkit.memory.memory_manager import MemoryManager
from codingkit.tools.registry import ToolRegistry


__all__ = [
    "ContextBuilder",
    "DEFAULT_SYSTEM_PROMPT",
]


#: The default system prompt used when no custom prompt is provided.
DEFAULT_SYSTEM_PROMPT = (
    "You are CodingKit, a coding agent that helps users write and debug code. "
    "You have access to a set of tools for reading, writing, and editing files, "
    "running commands and tests, searching code, and managing git operations. "
    "\n\n"
    "When you receive a task:\n"
    "1. Plan your approach before taking action.\n"
    "2. Use the available tools to implement your plan.\n"
    "3. When you run tests, examine the results carefully.\n"
    "4. If tests fail, the system will provide feedback about the failure. "
    "Use that feedback to decide what to fix.\n"
    "5. Provide a clear summary when the task is complete.\n"
    "\n"
    "When you need to run dangerous operations (shell commands, deleting files, "
    "installing dependencies, git operations), the system will ask the user for "
    "approval before executing.\n"
    "\n"
    "Be concise in your responses. Show the user what you're doing and why."
)


class ContextBuilder:
    """Builds the message list for an LLM call from all available context.

    Usage::

        builder = ContextBuilder(tool_registry)
        messages = builder.build(
            task="Write a test for the calculator module",
            history=previous_turns,
            memories=relevant_memories,
            feedback_ctx=feedback_context,
        )
        response = llm.generate(messages, tools=tool_defs)
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_history_turns: int = 20,
    ) -> None:
        """Initialize the context builder.

        Args:
            tool_registry: Registry of available tools (used to build tool
                definitions for the LLM).  If ``None``, a default registry
                is created.
            system_prompt: Custom system prompt.  Defaults to
                ``DEFAULT_SYSTEM_PROMPT``.
            max_history_turns: Maximum number of conversation turns to include
                from history.  Older turns are truncated.
        """
        self._tool_registry = tool_registry or ToolRegistry()
        self._system_prompt = system_prompt
        self._max_history_turns = max_history_turns

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        task: str = "",
        *,
        history: Optional[List[Dict[str, Any]]] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        feedback_ctx: Optional[FeedbackContext] = None,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build a complete message list for an LLM call.

        Args:
            task: The user's task description.
            history: Previous conversation turns (list of message dicts).
            memories: Relevant memories retrieved from ``MemoryManager``.
            feedback_ctx: Active feedback-loop context (from the ingester).
            system_prompt: Override the default system prompt for this call.

        Returns:
            A list of message dicts in CodingKit unified format.
        """
        messages: List[Dict[str, Any]] = []

        # --- System message ---
        sp = system_prompt or self._system_prompt
        messages.append({"role": "system", "content": sp})

        # --- Memories (as a brief context note) ---
        if memories:
            memory_text = self._format_memories(memories)
            messages.append({"role": "user", "content": memory_text})

        # --- Feedback context (if any) ---
        if feedback_ctx is not None:
            feedback_prompt = build_feedback_prompt(feedback_ctx)
            messages.append({"role": "user", "content": feedback_prompt})

        # --- History (previous turns) ---
        if history:
            # Truncate to max_history_turns (keep the most recent)
            truncated = history[-self._max_history_turns:]
            messages.extend(truncated)

        # --- Current task ---
        if task:
            messages.append({"role": "user", "content": task})

        return messages

    # ------------------------------------------------------------------
    # Tool definitions (for LLM tool_use / function_calling)
    # ------------------------------------------------------------------

    def tool_definitions(self) -> List[Dict[str, Any]]:
        """Build the tool definitions list expected by ``LLMClient.generate()``.

        Returns a list of dicts in the CodingKit unified tool format
        (``name``, ``description``, ``input_schema``).
        """
        definitions: List[Dict[str, Any]] = []
        for tool in self._tool_registry.list_all():
            params = tool.parameters
            definitions.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": params.get("properties", {}),
                    "required": params.get("required", []),
                },
            })
        return definitions

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_memories(memories: List[Dict[str, Any]]) -> str:
        """Format memory records into a concise context note."""
        if not memories:
            return ""
        lines = [
            "## Relevant Context from Past Sessions\n",
        ]
        for mem in memories:
            content = mem.get("content", "")
            metadata = mem.get("metadata", {})
            mtype = metadata.get("type", "note") if isinstance(metadata, dict) else "note"
            score = mem.get("score", "")
            score_str = f" (relevance: {score:.2f})" if isinstance(score, (int, float)) else ""
            lines.append(f"- **[{mtype}]**{score_str} {content}")
        return "\n".join(lines)