"""LLM client factory (PLAN T1.3).

Routes a model name to the right backend by prefix:

* ``claude*``                         -> ClaudeClient   (Anthropic)
* ``gpt*`` / ``o1*`` / ``o3*`` / ``o4*`` -> OpenAIClient  (OpenAI)
* ``deepseek*`` / ``glm*`` / ``kimi*`` / ``minimax*`` / ``qwen*``
                                     -> OpenAIClient pointed at the
                                        provider's OpenAI-compatible
                                        ``base_url`` (see ``PROVIDERS``)
* ``mock``                           -> MockLLMClient  (no network)
* anything else                       -> ValueError

The factory signature follows PLAN T1.3 exactly: ``create_llm_client(model,
api_key)``. ``api_key`` may be ``None`` for the mock client.
"""

from __future__ import annotations

from typing import Any, Optional

from codingkit.core.llm_client import ClaudeClient, LLMClient, MockLLMClient, OpenAIClient

__all__ = ["create_llm_client", "list_known_models", "known_prefixes", "PROVIDERS"]

#: OpenAI-compatible Chinese LLM providers. Each record is
#: ``(prefixes, display label, base_url, suggested model names)``. Routing is
#: by *prefix*, so a provider's newly released model works without a code
#: change as long as its name keeps one of the listed prefixes. ``prefixes`` is
#: a tuple so a provider can be reachable under several brand names
#: (e.g. Moonship ships models as both ``kimi-*`` and ``moonshot-*``).
PROVIDERS: list[tuple[tuple[str, ...], str, str, list[str]]] = [
    (
        ("deepseek",),
        "DeepSeek",
        "https://api.deepseek.com/v1",
        ["deepseek-chat", "deepseek-reasoner"],
    ),
    (
        ("glm",),
        "Zhipu GLM (智谱)",
        "https://open.bigmodel.cn/api/paas/v4",
        ["glm-4.6", "glm-4.5", "glm-4-plus", "glm-4-flash", "glm-4-flashx"],
    ),
    (
        ("kimi", "moonshot"),
        "Moonshot Kimi",
        "https://api.moonshot.cn/v1",
        ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-k2"],
    ),
    (
        ("minimax",),
        "MiniMax",
        "https://api.minimax.chat/v1",
        ["MiniMax-M1", "minimax-text-01", "abab6.5s-chat"],
    ),
    (
        ("qwen",),
        "Qwen (DashScope 通义)",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ["qwen-max", "qwen-plus", "qwen-turbo", "qwen3-235b-a22b"],
    ),
]

#: The non-provider prefixes the factory also recognises.
_BASE_PREFIXES: tuple[str, ...] = ("claude", "gpt", "o1", "o3", "o4", "mock")


def known_prefixes() -> tuple[str, ...]:
    """All model-name prefixes the factory can route (providers + base)."""
    provider_prefixes = [p for prefixes, _l, _u, _m in PROVIDERS for p in prefixes]
    return _BASE_PREFIXES + tuple(provider_prefixes)


def list_known_models() -> dict[str, list[str]]:
    """Return ``{provider_label: [model names]}`` for the CLI catalog.

    Includes the built-in Anthropic / OpenAI / Mock groups alongside the
    OpenAI-compatible providers in ``PROVIDERS``.
    """
    catalog: dict[str, list[str]] = {
        "Anthropic Claude": ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"],
        "OpenAI": ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
        "Mock (testing)": ["mock"],
    }
    for _prefixes, label, _base_url, models in PROVIDERS:
        catalog[label] = list(models)
    return catalog


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
    for prefixes, _label, base_url, _models in PROVIDERS:
        if name.startswith(prefixes):
            return OpenAIClient(model=model, api_key=api_key, base_url=base_url, **kwargs)

    raise ValueError(
        f"Unknown model {model!r}: cannot pick a provider. "
        f"Supported prefixes: {', '.join(known_prefixes())}."
    )

