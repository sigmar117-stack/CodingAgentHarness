"""LLM abstraction layer (PLAN T1.3).

A single ``LLMClient`` interface with three concrete backends:

* ``ClaudeClient``   — Anthropic SDK, native tool_use
* ``OpenAIClient``    — OpenAI SDK, native function calling
* ``MockLLMClient``   — returns canned responses in order; needs no SDK, no network

Unified contract (CodingKit-native) so the agent loop talks to one shape:

Message (dict) ::
    {"role": "user" | "assistant",
     "content": str | list[Block]}

    {"role": "tool",                 # a tool result fed back to the model
     "tool_use_id": str,
     "content": str}

Block (dict) :: one of
    {"type": "text",       "text": str}
    {"type": "tool_use",   "id": str, "name": str, "input": dict}
    {"type": "tool_result","tool_use_id": str, "content": str}

Tool (dict) ::
    {"name": str, "description": str, "input_schema": <JSON Schema dict>}

LLMResponse :: {content: str, tool_calls: list[ToolCall], model: str, usage: dict}

The per-provider translation functions (``_messages_to_anthropic`` etc.) are
module-level and unit-tested directly, so the adapter logic is verifiable
without an API key.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "ToolCall",
    "LLMResponse",
    "LLMClient",
    "ClaudeClient",
    "OpenAIClient",
    "MockLLMClient",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""

    name: str
    arguments: dict
    id: Optional[str] = None  # Anthropic ``tool_use`` id / OpenAI ``call_id``


@dataclass
class LLMResponse:
    """Normalized response returned by every ``LLMClient.generate``."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract client
# ---------------------------------------------------------------------------


class LLMClient(ABC):
    """Provider-agnostic LLM client."""

    @abstractmethod
    def generate(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a response given ``messages`` and optional ``tools``."""


# ---------------------------------------------------------------------------
# Translation helpers — unified <-> provider-native
# ---------------------------------------------------------------------------


def _content_to_text(content: Any) -> str:
    """Flatten a message ``content`` (str or block list) to plain text."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


def _content_tool_uses(content: Any) -> list[dict]:
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
    return []


# --- to Anthropic ----------------------------------------------------------


def _messages_to_anthropic(messages: list[dict]) -> list[dict]:
    """Convert unified messages to Anthropic's messages format.

    Anthropic requires ``tool_result`` blocks inside a ``user`` message; our
    ``tool``-role messages are therefore merged into ``user`` messages. The
    first message must be ``user`` (Anthropic requirement) — that is the
    caller's responsibility.
    """
    out: list[dict] = []
    for msg in messages:
        role = msg["role"]
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": msg["tool_use_id"],
                "content": msg["content"],
            }
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue

        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
        else:
            blocks = []
            for b in content or []:
                t = b.get("type")
                if t == "text":
                    blocks.append({"type": "text", "text": b.get("text", "")})
                elif t == "tool_use":
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": b.get("id"),
                            "name": b.get("name"),
                            "input": b.get("input", {}),
                        }
                    )
                elif t == "tool_result":
                    blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": b.get("tool_use_id"),
                            "content": b.get("content", ""),
                        }
                    )
            out.append({"role": role, "content": blocks})
    return out


def _tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Anthropic tool schema already matches our unified shape."""
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("input_schema", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]


# --- to OpenAI -------------------------------------------------------------


def _messages_to_openai(messages: list[dict]) -> list[dict]:
    """Convert unified messages to OpenAI chat-completions format."""
    out: list[dict] = []
    for msg in messages:
        role = msg["role"]
        if role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg["tool_use_id"],
                    "content": msg["content"],
                }
            )
            continue

        content = msg.get("content")
        text = _content_to_text(content)
        tool_uses = _content_tool_uses(content)

        if role == "assistant" and tool_uses:
            out.append(
                {
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": [
                        {
                            "id": tu.get("id"),
                            "type": "function",
                            "function": {
                                "name": tu.get("name"),
                                "arguments": json.dumps(tu.get("input", {}), ensure_ascii=False),
                            },
                        }
                        for tu in tool_uses
                    ],
                }
            )
        else:
            out.append({"role": role, "content": text})
    return out


def _tools_to_openai(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


# ---------------------------------------------------------------------------
# ClaudeClient (Anthropic)
# ---------------------------------------------------------------------------


class ClaudeClient(LLMClient):
    """Anthropic Claude client with native tool_use support."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        client: Any = None,
        max_tokens: int = 4096,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        if client is not None:
            # Dependency injection — used by tests to avoid the network.
            self._client = client
        else:
            import anthropic  # noqa: PLC0415 — lazy import (optional `llm` extra)

            self._client = anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": _messages_to_anthropic(messages),
            "max_tokens": kwargs.pop("max_tokens", self._max_tokens),
        }
        if tools:
            payload["tools"] = _tools_to_anthropic(tools)
        payload.update(kwargs)

        raw = self._client.messages.create(**payload)
        return self._parse_response(raw, self._model)

    @staticmethod
    def _parse_response(raw: Any, model: str) -> LLMResponse:
        # Support both SDK response objects and plain dicts (tests).
        content_blocks = getattr(raw, "content", None)
        if content_blocks is None and isinstance(raw, dict):
            content_blocks = raw.get("content", [])
        usage_obj = getattr(raw, "usage", None)
        if usage_obj is None and isinstance(raw, dict):
            usage_obj = raw.get("usage", {})

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in content_blocks or []:
            btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if btype == "text":
                txt = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                text_parts.append(txt or "")
            elif btype == "tool_use":
                if isinstance(block, dict):
                    tool_calls.append(
                        ToolCall(
                            name=block.get("name", ""),
                            arguments=block.get("input", {}),
                            id=block.get("id"),
                        )
                    )
                else:
                    tool_calls.append(
                        ToolCall(
                            name=getattr(block, "name", ""),
                            arguments=getattr(block, "input", {}),
                            id=getattr(block, "id", None),
                        )
                    )

        usage = {}
        if isinstance(usage_obj, dict):
            usage = dict(usage_obj)
        elif usage_obj is not None:
            usage = {k: getattr(usage_obj, k) for k in dir(usage_obj) if not k.startswith("_")}

        return LLMResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            model=model,
            usage=usage,
        )


# ---------------------------------------------------------------------------
# OpenAIClient
# ---------------------------------------------------------------------------


class OpenAIClient(LLMClient):
    """OpenAI client with native function-calling support."""

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        client: Any = None,
    ) -> None:
        self._model = model
        if client is not None:
            self._client = client
        else:
            import openai  # noqa: PLC0415 — lazy import (optional `llm` extra)

            self._client = openai.OpenAI(api_key=api_key)

    def generate(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": _messages_to_openai(messages),
        }
        if tools:
            payload["tools"] = _tools_to_openai(tools)
        payload.update(kwargs)

        raw = self._client.chat.completions.create(**payload)
        return self._parse_response(raw, self._model)

    @staticmethod
    def _parse_response(raw: Any, model: str) -> LLMResponse:
        # Normalize to a dict.
        if isinstance(raw, dict):
            raw_dict = raw
        else:
            raw_dict = raw.model_dump() if hasattr(raw, "model_dump") else {}

        choices = raw_dict.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        content = message.get("content") or ""
        raw_tool_calls = message.get("tool_calls") or []

        tool_calls: list[ToolCall] = []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            args_raw = fn.get("arguments", "{}")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(ToolCall(name=fn.get("name", ""), arguments=args, id=tc.get("id")))

        usage = raw_dict.get("usage", {}) or {}

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model=raw_dict.get("model", model),
            usage=dict(usage),
        )


# ---------------------------------------------------------------------------
# MockLLMClient
# ---------------------------------------------------------------------------


class MockLLMClient(LLMClient):
    """Deterministic client for unit tests. Returns canned responses in order.

    Accepts a list whose entries may be ``LLMResponse``, ``dict`` (with the
    ``LLMResponse`` fields), or plain ``str`` (becomes the ``content``).
    """

    def __init__(self, responses: Optional[list[Any]] = None, model: str = "mock") -> None:
        self._responses: list[Any] = list(responses or [])
        self._model = model
        self._index = 0
        self.calls: list[dict] = []  # records each generate() invocation

    @staticmethod
    def _coerce(item: Any, model: str) -> LLMResponse:
        if isinstance(item, LLMResponse):
            return item
        if isinstance(item, str):
            return LLMResponse(content=item, model=model)
        if isinstance(item, dict):
            return LLMResponse(
                content=item.get("content", ""),
                tool_calls=[ToolCall(**tc) if isinstance(tc, dict) else tc for tc in item.get("tool_calls", [])],
                model=item.get("model", model),
                usage=item.get("usage", {}),
            )
        raise TypeError(f"Unsupported mock response entry: {type(item)!r}")

    def generate(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools, "kwargs": kwargs})
        if self._index >= len(self._responses):
            # Exhausted — return an empty response (deterministic, no error).
            return LLMResponse(content="", model=self._model)
        item = self._responses[self._index]
        self._index += 1
        return self._coerce(item, self._model)
