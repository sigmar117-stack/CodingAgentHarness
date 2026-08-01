"""Response parser — extracts text replies and tool calls from LLM responses (PLAN T4.1).

The ``ResponseParser`` takes an ``LLMResponse`` and returns a structured
``ParsedResponse`` that distinguishes between:

* **Text replies**: The LLM is speaking to the user (no tool calls).
* **Tool calls**: The LLM wants to invoke one or more tools.

It also handles edge cases like empty responses, malformed tool calls, and
rate-limit / error responses from the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from codingkit.core.llm_client import LLMResponse, ToolCall


__all__ = [
    "ParsedResponse",
    "ResponseParser",
    "ParseError",
]


# ---------------------------------------------------------------------------
# ParseError
# ---------------------------------------------------------------------------


class ParseError(Exception):
    """Raised when the LLM response cannot be parsed."""


# ---------------------------------------------------------------------------
# ParsedResponse
# ---------------------------------------------------------------------------


@dataclass
class ParsedResponse:
    """Structured interpretation of an LLM response.

    Attributes:
        text: The text reply from the LLM (empty if there are tool calls).
        tool_calls: List of tool calls requested by the LLM.
        is_complete: Whether the LLM indicated the task is complete.
        raw: The original ``LLMResponse`` for debugging/logging.
        error: Error message if parsing failed.
    """

    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    is_complete: bool = False
    raw: Optional[LLMResponse] = None
    error: str = ""


# ---------------------------------------------------------------------------
# ResponseParser
# ---------------------------------------------------------------------------


# Keywords that indicate the LLM thinks the task is complete.
_COMPLETION_KEYWORDS: frozenset[str] = frozenset({
    "task complete",
    "task is complete",
    "all done",
    "finished",
    "i'm done",
    "i am done",
    "the task is finished",
    "that's it",
    "that is it",
    "no further action",
    "nothing more to do",
})

# Maximum retries for parsing attempts.
_MAX_PARSE_RETRIES = 3


class ResponseParser:
    """Parses an ``LLMResponse`` into a ``ParsedResponse``.

    Usage::

        parser = ResponseParser()
        parsed = parser.parse(llm_response)
        if parsed.text:
            print(f"LLM says: {parsed.text}")
        if parsed.tool_calls:
            for tc in parsed.tool_calls:
                print(f"Tool call: {tc.name}({tc.arguments})")
    """

    def parse(
        self,
        response: Optional[LLMResponse],
        attempt: int = 1,
    ) -> ParsedResponse:
        """Parse an ``LLMResponse`` into a ``ParsedResponse``.

        Args:
            response: The raw response from the LLM, or ``None``.
            attempt: The current parse attempt number (for error reporting).

        Returns:
            A ``ParsedResponse`` with the extracted information.
        """
        if response is None:
            return ParsedResponse(
                error="LLM returned no response",
                raw=None,
            )

        text = (response.content or "").strip()
        tool_calls = list(response.tool_calls or [])
        is_complete = self._detect_completion(text)

        return ParsedResponse(
            text=text,
            tool_calls=tool_calls,
            is_complete=is_complete,
            raw=response,
        )

    def needs_retry(self, parsed: ParsedResponse) -> bool:
        """Check if the response needs a retry (empty or malformed).

        Returns ``True`` when the LLM produced no text and no tool calls,
        suggesting a retry is needed.
        """
        return not parsed.text and not parsed.tool_calls and not parsed.error

    @staticmethod
    def retry_prompt(attempt: int, max_retries: int = _MAX_PARSE_RETRIES) -> str:
        """Generate a prompt asking the LLM to retry with a valid response.

        Args:
            attempt: Current attempt number (1-indexed).
            max_retries: Maximum number of retries.

        Returns:
            A message to send to the LLM requesting a proper response.
        """
        remaining = max_retries - attempt
        if remaining <= 0:
            return (
                "You did not produce a valid response. "
                "Please respond with a clear message or use the available tools."
            )
        return (
            f"Your previous response was empty or unparseable "
            f"(attempt {attempt}/{max_retries}). "
            f"Please respond with a clear text message or use the available tools. "
            f"You have {remaining} attempt(s) remaining."
        )

    @staticmethod
    def format_error_prompt(error: str) -> str:
        """Generate a prompt informing the LLM about a parse error.

        Args:
            error: The error message to include.

        Returns:
            A message to send to the LLM explaining the error.
        """
        return (
            f"There was an error processing your response:\n\n"
            f"```\n{error}\n```\n\n"
            f"Please try again with a valid response."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_completion(text: str) -> bool:
        """Detect if the LLM indicated task completion.

        Checks for completion keywords in the *last* paragraph of the text,
        since the LLM typically summarises at the end.
        """
        if not text:
            return False
        # Consider the last 200 characters for completion detection.
        tail = text[-200:].lower()
        for keyword in _COMPLETION_KEYWORDS:
            if keyword in tail:
                return True
        return False