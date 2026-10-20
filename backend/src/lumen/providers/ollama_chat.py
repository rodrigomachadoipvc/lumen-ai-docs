"""Chat through a local Ollama server."""

import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any

import ollama

from lumen.providers.chat import (
    ChatCompletion,
    ChatEvent,
    ChatMessage,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from lumen.providers.errors import ProviderError


def to_ollama_messages(system: str, messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        if message.role == "tool":
            converted.append(
                {"role": "tool", "content": message.content, "tool_name": message.tool_name}
            )
            continue
        item: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            item["tool_calls"] = [
                {"function": {"name": call.name, "arguments": call.arguments}}
                for call in message.tool_calls
            ]
        converted.append(item)
    return converted


def to_ollama_tools(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


class OllamaChat:
    def __init__(self, *, base_url: str, model: str, think: bool, context_tokens: int) -> None:
        self._client = ollama.AsyncClient(host=base_url)
        self._base_url = base_url
        self._model = model
        self._think = think
        self._context_tokens = context_tokens

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
        calls: list[ToolCall] = []
        done_reason = "stop"
        usage: dict[str, int] = {}
        try:
            response = await self._client.chat(
                model=self._model,
                messages=to_ollama_messages(system, messages),
                tools=to_ollama_tools(tools) or None,
                stream=True,
                think=self._think,
                options={"num_ctx": self._context_tokens},
                # Keep the model in memory between questions; loading it takes ~10 s.
                keep_alive="30m",
            )
            async for part in response:
                if part.message.content:
                    text_parts.append(part.message.content)
                    yield TextDelta(part.message.content)
                for call in part.message.tool_calls or []:
                    calls.append(
                        ToolCall(
                            id=f"call_{uuid.uuid4().hex[:12]}",
                            name=call.function.name,
                            arguments=dict(call.function.arguments),
                        )
                    )
                if part.done:
                    done_reason = part.done_reason or "stop"
                    usage = {
                        "input_tokens": part.prompt_eval_count or 0,
                        "output_tokens": part.eval_count or 0,
                    }
        except ConnectionError as exc:
            raise ProviderError(
                f"Could not reach Ollama at {self._base_url}. Is it running?"
            ) from exc
        except ollama.ResponseError as exc:
            hint = f" Run `ollama pull {self._model}`." if exc.status_code == 404 else ""
            raise ProviderError(f"Ollama chat failed: {exc.error}.{hint}") from exc

        stop_reason = "tool_calls" if calls else ("length" if done_reason == "length" else "stop")
        yield ChatCompletion(
            text="".join(text_parts), tool_calls=tuple(calls), stop_reason=stop_reason, usage=usage
        )
