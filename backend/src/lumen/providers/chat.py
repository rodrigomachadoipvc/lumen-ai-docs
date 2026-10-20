"""Provider-neutral chat interface: streaming text plus tool calling.

Every adapter turns the same `ChatMessage` history into its provider's format and yields
`TextDelta` events while the model writes, then exactly one `ChatCompletion` at the end.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from lumen.config import Settings
from lumen.providers.errors import ProviderError


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    # JSON Schema for the arguments object.
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    # For role="tool": which call this answers.
    tool_call_id: str | None = None
    tool_name: str | None = None
    # Provider-specific copy of an assistant turn (e.g. Anthropic content blocks with thinking),
    # sent back verbatim within the same agent loop so nothing the model produced is edited.
    raw: Any = None


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ChatCompletion:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    # "stop", "tool_calls", "length" or "refusal".
    stop_reason: str = "stop"
    raw: Any = None
    usage: dict[str, int] = field(default_factory=dict)


ChatEvent = TextDelta | ChatCompletion


class ChatProvider(Protocol):
    @property
    def model(self) -> str: ...

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[ChatEvent]: ...


DEFAULT_CHAT_MODELS = {
    "ollama": "qwen3.5:4b",
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-6-luna",
}


def build_chat_provider(settings: Settings) -> ChatProvider:
    model = settings.chat_model or DEFAULT_CHAT_MODELS[settings.chat_provider]
    match settings.chat_provider:
        case "anthropic":
            from lumen.providers.anthropic_chat import AnthropicChat

            if settings.anthropic_api_key is None:
                raise ProviderError(
                    "LUMEN_ANTHROPIC_API_KEY is required for the Anthropic provider."
                )
            return AnthropicChat(
                api_key=settings.anthropic_api_key.get_secret_value(),
                model=model,
                effort=settings.anthropic_effort,
                max_tokens=settings.chat_max_tokens,
            )
        case "openai":
            from lumen.providers.openai_chat import OpenAIChat

            if settings.openai_api_key is None:
                raise ProviderError("LUMEN_OPENAI_API_KEY is required for the OpenAI provider.")
            return OpenAIChat(
                api_key=settings.openai_api_key.get_secret_value(),
                model=model,
                max_tokens=settings.chat_max_tokens,
            )
        case "ollama":
            from lumen.providers.ollama_chat import OllamaChat

            return OllamaChat(
                base_url=settings.ollama_base_url,
                model=model,
                think=settings.ollama_think,
                context_tokens=settings.ollama_context_tokens,
            )
