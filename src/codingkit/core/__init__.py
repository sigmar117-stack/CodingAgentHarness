"""Core building blocks: agent loop, LLM client, credential store, context builder, response parser, sessions."""

from codingkit.core.agent_loop import MAX_TURNS, AgentLoop, LoopResult, LoopState, TurnRecord
from codingkit.core.context_builder import DEFAULT_SYSTEM_PROMPT, ContextBuilder
from codingkit.core.credential_store import (
    CredentialStore,
    EncryptedFileStore,
    KeychainStore,
    get_credential_store,
)
from codingkit.core.llm_client import (
    ClaudeClient,
    LLMClient,
    LLMResponse,
    MockLLMClient,
    OpenAIClient,
    ToolCall,
)
from codingkit.core.llm_factory import create_llm_client
from codingkit.core.response_parser import ParsedResponse, ParseError, ResponseParser
