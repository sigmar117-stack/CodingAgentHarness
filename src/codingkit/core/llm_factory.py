"""LLM client factory (PLAN T1.3).

Routes a model name to the right backend by prefix:

* ``claude*``            -> ClaudeClient   (Anthropic)
* ``gpt*`` / ``o1*``     -> OpenAIClient   (OpenAI)
* ``mock``               -> MockLLMClient  (no network)
* anything else          -> ValueError

The factory signature follows PLAN T1.3 exactly: ``create_llm_client(model,
api_key)``. ``api_key`` may be ``None`` for the mock client.
"""

from __future__ import annotations

from typing import Any, Optional

from codingkit.core.llm_client import ClaudeClient, LLMClient, MockLLMClient, OpenAIClient

__all__ = ["create_llm_client"]


def create_llm_client(
    model: str,
    api_key: Optional[str] = None,
    **kwargs: Any,
) -> LLMClient:
    """Build an ``LLMClient`` for ``model``, routing by model-name prefix.

    Raises ``ValueError`` for unknown model families.
    """
    name = (model or "").strip().lower()

    if name == "mock" or name.startswith("mock"):
        return MockLLMClient(**kwargs)
    if name.startswith("claude"):
        return ClaudeClient(model=model, api_key=api_key, **kwargs)
    if name.startswith(("gpt", "o1", "o3", "o4")):
        return OpenAIClient(model=model, api_key=api_key, **kwargs)

    raise ValueError(
        f"Unknown model {model!r}: cannot pick a provider. "
        f"Supported prefixes: claude*, gpt*, o1*, mock."
    )
