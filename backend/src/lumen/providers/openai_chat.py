"""Chat through the OpenAI Chat Completions API, with streaming and function calling."""

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import openai

from lumen.providers.chat import (
    ChatCompletion,
    ChatEvent,
    ChatMessage,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from lumen.providers.errors import ProviderError


def to_openai_messages(system: str, messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        if message.role == "tool":
            converted.append(
                {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
            )
            continue
        item: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            item["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in message.tool_calls
            ]
        converted.append(item)
    return converted


class OpenAIChat:
    def __init__(self, *, api_key: str, model: str, max_tokens: int) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
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
        text_parts: list[str] = []
        partial_calls: dict[int, dict[str, str]] = {}
        finish_reason = "stop"
        request: dict[str, Any] = {
            "model": self._model,
            "messages": to_openai_messages(system, messages),
            "max_completion_tokens": self._max_tokens,
            "stream": True,
        }
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        try:
            stream = await self._client.chat.completions.create(**request)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    text_parts.append(delta.content)
                    yield TextDelta(delta.content)
                for call in delta.tool_calls or []:
                    entry = partial_calls.setdefault(call.index, {"id": "", "name": "", "args": ""})
                    if call.id:
                        entry["id"] = call.id
                    if call.function and call.function.name:
                        entry["name"] = call.function.name
                    if call.function and call.function.arguments:
                        entry["args"] += call.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
        except openai.AuthenticationError as exc:
            raise ProviderError("The OpenAI API key was rejected.") from exc
        except openai.OpenAIError as exc:
            raise ProviderError(f"OpenAI chat failed: {exc}") from exc

        calls: list[ToolCall] = []
        for entry in partial_calls.values():
            try:
                arguments = json.loads(entry["args"] or "{}")
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                ToolCall(
                    id=entry["id"],
                    name=entry["name"],
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
        stop_reason = "tool_calls" if calls else ("length" if finish_reason == "length" else "stop")
        yield ChatCompletion(
            text="".join(text_parts), tool_calls=tuple(calls), stop_reason=stop_reason
        )
