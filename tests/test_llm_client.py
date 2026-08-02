"""Tests for the LLM abstraction layer (PLAN T1.3).

No network, no real API keys. Real ``ClaudeClient`` / ``OpenAIClient`` adapters
are exercised via injected fake SDK clients; the translation functions are
tested directly.
"""

from __future__ import annotations

import json

import pytest

from codingkit.core.llm_client import (
    ClaudeClient,
    LLMResponse,
    MockLLMClient,
    OpenAIClient,
    ToolCall,
    _messages_to_anthropic,
    _messages_to_openai,
    _tools_to_anthropic,
    _tools_to_openai,
)
from codingkit.core.llm_factory import create_llm_client

# --- MockLLMClient (PLAN T1.3 verification) ---------------------------------


def test_mock_returns_responses_in_order() -> None:
    """PLAN T1.3 ① — injected responses come back in order."""
    client = MockLLMClient(
        responses=[
            "first",
            LLMResponse(content="second", tool_calls=[ToolCall(name="t", arguments={"x": 1}, id="1")]),
            {"content": "third", "tool_calls": [{"name": "t2", "arguments": {}}]},
        ]
    )
    r1 = client.generate(messages=[{"role": "user", "content": "hi"}])
    assert r1.content == "first"
    assert r1.tool_calls == []

    r2 = client.generate(messages=[{"role": "user", "content": "hi"}])
    assert r2.content == "second"
    assert len(r2.tool_calls) == 1
    assert r2.tool_calls[0].name == "t"
    assert r2.tool_calls[0].arguments == {"x": 1}

    r3 = client.generate(messages=[{"role": "user", "content": "hi"}])
    assert r3.content == "third"
    assert r3.tool_calls[0].name == "t2"


def test_mock_empty_responses_returns_empty() -> None:
    """PLAN T1.3 ② — empty response list yields an empty response."""
    client = MockLLMClient(responses=[])
    resp = client.generate(messages=[{"role": "user", "content": "hi"}])
    assert resp.content == ""
    assert resp.tool_calls == []
    assert resp.model == "mock"


def test_mock_exhausted_returns_empty() -> None:
    """Once exhausted, subsequent calls return empty (no error)."""
    client = MockLLMClient(responses=["only"])
    client.generate(messages=[{"role": "user", "content": "hi"}])
    again = client.generate(messages=[{"role": "user", "content": "hi"}])
    assert again.content == ""


def test_mock_records_calls() -> None:
    client = MockLLMClient(responses=["ok"])
    client.generate(messages=[{"role": "user", "content": "hi"}], tools=[{"name": "t"}])
    assert len(client.calls) == 1
    assert client.calls[0]["tools"] == [{"name": "t"}]


# --- Factory (PLAN T1.3 verification) --------------------------------------


def test_factory_routes_claude() -> None:
    client = create_llm_client("claude-sonnet-5", api_key="dummy")
    assert isinstance(client, ClaudeClient)


def test_factory_routes_openai() -> None:
    client = create_llm_client("gpt-4o", api_key="dummy")
    assert isinstance(client, OpenAIClient)


def test_factory_routes_mock() -> None:
    client = create_llm_client("mock", api_key=None)
    assert isinstance(client, MockLLMClient)


def test_factory_invalid_model_raises() -> None:
    """PLAN T1.3 ③ — unknown model name raises ValueError."""
    with pytest.raises(ValueError, match="Unknown model"):
        create_llm_client("llama-3-70b", api_key="dummy")


# --- Translation: unified -> Anthropic -------------------------------------


def test_anthropic_text_message() -> None:
    out = _messages_to_anthropic([{"role": "user", "content": "hello"}])
    assert out == [{"role": "user", "content": "hello"}]


def test_anthropic_assistant_tool_use_then_tool_result() -> None:
    """A tool-role message must land as a tool_result block in a user message."""
    msgs = [
        {"role": "user", "content": "list files"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu_1", "name": "search_files", "input": {"pattern": "*.py"}},
        ]},
        {"role": "tool", "tool_use_id": "tu_1", "content": "a.py\nb.py"},
    ]
    out = _messages_to_anthropic(msgs)
    assert len(out) == 3
    assert out[0] == {"role": "user", "content": "list files"}
    assert out[1]["role"] == "assistant"
    assert out[1]["content"][0]["type"] == "tool_use"
    assert out[1]["content"][0]["input"] == {"pattern": "*.py"}
    # tool-role message became a user message with a tool_result block
    assert out[2]["role"] == "user"
    assert out[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "tu_1",
        "content": "a.py\nb.py",
    }


def test_anthropic_consecutive_tool_results_merge() -> None:
    msgs = [
        {"role": "tool", "tool_use_id": "a", "content": "r1"},
        {"role": "tool", "tool_use_id": "b", "content": "r2"},
    ]
    out = _messages_to_anthropic(msgs)
    assert len(out) == 1
    assert out[0]["role"] == "user"
    assert [b["tool_use_id"] for b in out[0]["content"]] == ["a", "b"]


def test_tools_to_anthropic_passes_schema() -> None:
    tools = [{"name": "read_file", "description": "read", "input_schema": {"type": "object"}}]
    out = _tools_to_anthropic(tools)
    assert out[0] == {
        "name": "read_file",
        "description": "read",
        "input_schema": {"type": "object"},
    }


# --- Translation: unified -> OpenAI -----------------------------------------


def test_openai_text_messages() -> None:
    out = _messages_to_openai([{"role": "user", "content": "hi"}])
    assert out == [{"role": "user", "content": "hi"}]


def test_openai_assistant_with_tool_use() -> None:
    msgs = [
        {"role": "assistant", "content": [
            {"type": "text", "text": "calling"},
            {"type": "tool_use", "id": "c1", "name": "t", "input": {"x": 1}},
        ]},
    ]
    out = _messages_to_openai(msgs)
    assert out[0]["role"] == "assistant"
    assert out[0]["content"] == "calling"
    tc = out[0]["tool_calls"][0]
    assert tc["id"] == "c1"
    assert tc["type"] == "function"
    assert json.loads(tc["function"]["arguments"]) == {"x": 1}


def test_openai_tool_role_message() -> None:
    out = _messages_to_openai(
        [{"role": "tool", "tool_use_id": "c1", "content": "result"}]
    )
    assert out == [{"role": "tool", "tool_call_id": "c1", "content": "result"}]


def test_tools_to_openai_wraps_function() -> None:
    tools = [{"name": "read_file", "description": "read", "input_schema": {"type": "object"}}]
    out = _tools_to_openai(tools)
    assert out[0] == {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "read",
            "parameters": {"type": "object"},
        },
    }


# --- Real adapter generate() via injected fake SDK clients ------------------


class _FakeAnthropicMessages:
    def __init__(self, response: dict) -> None:
        self._response = response
        self.last_payload: dict = {}

    def create(self, **payload):
        self.last_payload = payload
        return self._response


class _FakeAnthropic:
    def __init__(self, response: dict) -> None:
        self.messages = _FakeAnthropicMessages(response)


def test_claude_generate_parses_text_and_tool_use() -> None:
    fake_response = {
        "content": [
            {"type": "text", "text": "I will read the file."},
            {"type": "tool_use", "id": "tu_9", "name": "read_file", "input": {"path": "a.py"}},
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    fake = _FakeAnthropic(fake_response)
    client = ClaudeClient(model="claude-sonnet-5", client=fake)

    resp = client.generate(
        messages=[{"role": "user", "content": "read a.py"}],
        tools=[{"name": "read_file", "description": "read", "input_schema": {"type": "object"}}],
    )
    assert resp.content == "I will read the file."
    assert resp.model == "claude-sonnet-5"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "read_file"
    assert resp.tool_calls[0].arguments == {"path": "a.py"}
    assert resp.tool_calls[0].id == "tu_9"
    assert resp.usage == {"input_tokens": 10, "output_tokens": 5}

    # The adapter must translate messages + tools to Anthropic's format.
    sent = fake.messages.last_payload
    assert sent["model"] == "claude-sonnet-5"
    assert sent["messages"] == [{"role": "user", "content": "read a.py"}]
    assert sent["tools"][0]["name"] == "read_file"
    assert "input_schema" in sent["tools"][0]


class _FakeChatCompletions:
    def __init__(self, response: dict) -> None:
        self._response = response
        self.last_payload: dict = {}

    def create(self, **payload):
        self.last_payload = payload
        return self._response


class _FakeOpenAI:
    def __init__(self, response: dict) -> None:
        self.chat = type("_Chat", (), {"completions": _FakeChatCompletions(response)})()


def test_openai_generate_parses_text_and_function_call() -> None:
    fake_response = {
        "model": "gpt-4o",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "I will read the file.",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "a.py"}),
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
    }
    fake = _FakeOpenAI(fake_response)
    client = OpenAIClient(model="gpt-4o", client=fake)

    resp = client.generate(
        messages=[{"role": "user", "content": "read a.py"}],
        tools=[{"name": "read_file", "description": "read", "input_schema": {"type": "object"}}],
    )
    assert resp.content == "I will read the file."
    assert resp.model == "gpt-4o"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "read_file"
    assert resp.tool_calls[0].arguments == {"path": "a.py"}
    assert resp.tool_calls[0].id == "call_1"

    sent = fake.chat.completions.last_payload
    assert sent["messages"] == [{"role": "user", "content": "read a.py"}]
    assert sent["tools"][0]["type"] == "function"
    assert sent["tools"][0]["function"]["name"] == "read_file"


def test_openai_generate_handles_malformed_arguments() -> None:
    """Bad JSON in tool-call arguments must not crash the parser."""
    fake_response = {
        "model": "gpt-4o",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "t", "arguments": "not-json"},
                        }
                    ],
                }
            }
        ],
    }
    fake = _FakeOpenAI(fake_response)
    resp = OpenAIClient(model="gpt-4o", client=fake).generate(messages=[{"role": "user", "content": "x"}])
    assert resp.tool_calls[0].arguments == {}
