"""Chat through the Anthropic Messages API (Claude), with streaming and tool use."""

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal

import anthropic

from lumen.providers.chat import (
    ChatCompletion,
    ChatEvent,
    ChatMessage,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from lumen.providers.errors import ProviderError

Effort = Literal["low", "medium", "high"]


def to_anthropic_messages(messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    """Tool results for one assistant turn are sent together in a single user message."""
    converted: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []

    def flush_results() -> None:
        if pending_results:
            converted.append({"role": "user", "content": list(pending_results)})
            pending_results.clear()

    for message in messages:
        if message.role == "tool":
            pending_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": message.content,
                }
            )
            continue
        flush_results()
        if message.role == "assistant" and message.raw is not None:
            # The exact blocks Claude produced (thinking, text, tool_use), unedited.
            converted.append({"role": "assistant", "content": message.raw})
        elif message.role == "assistant" and message.tool_calls:
            blocks: list[dict[str, Any]] = []
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            blocks.extend(
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                for c in message.tool_calls
            )
            converted.append({"role": "assistant", "content": blocks})
        else:
            converted.append({"role": message.role, "content": message.content})
    flush_results()
    return converted


def to_anthropic_tools(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    # Tool inputs here are small; eager input streaming would only add client-side validation work.
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
    ]


class AnthropicChat:
    def __init__(self, *, api_key: str, model: str, effort: Effort, max_tokens: int) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[ChatEvent]:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": to_anthropic_messages(messages),
            "output_config": {"effort": self._effort},
            # If a safety classifier declines, the API retries on a suitable fallback model.
            "betas": ["server-side-fallback-2026-07-01"],
            "fallbacks": "default",
        }
        if tools:
            request["tools"] = to_anthropic_tools(tools)
        try:
            async with self._client.beta.messages.stream(**request) as stream:
                async for text in stream.text_stream:
                    yield TextDelta(text)
                final = await stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise ProviderError("The Anthropic API key was rejected.") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("Anthropic rate limit reached; try again shortly.") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Could not reach the Anthropic API.") from exc

        calls = tuple(
            ToolCall(id=b.id, name=b.name, arguments=_as_dict(b.input))
            for b in final.content
            if b.type == "tool_use"
        )
        text = "".join(b.text for b in final.content if b.type == "text")
        stop_reason = {
            "tool_use": "tool_calls",
            "max_tokens": "length",
            "refusal": "refusal",
        }.get(final.stop_reason or "", "stop")
        yield ChatCompletion(
            text=text,
            tool_calls=calls,
            stop_reason=stop_reason,
            raw=[block.model_dump(exclude_none=True) for block in final.content],
            usage={
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
            },
        )


def _as_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}
