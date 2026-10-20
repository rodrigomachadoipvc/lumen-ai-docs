"""Deterministic stand-ins for model providers."""

import hashlib
import math
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from lumen.config import EMBEDDING_DIMENSIONS
from lumen.providers.chat import ChatCompletion, ChatEvent, ChatMessage, TextDelta, ToolSpec

_WORD = re.compile(r"\w+", re.UNICODE)


def hashed_bag_of_words(text: str) -> list[float]:
    """Texts that share words get similar vectors, which is enough to test vector search."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for word in _WORD.findall(text.lower()):
        digest = hashlib.blake2b(word.encode(), digest_size=4).digest()
        vector[int.from_bytes(digest) % EMBEDDING_DIMENSIONS] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector] if any(vector) else [1.0] + [0.0] * (len(vector) - 1)


class FakeEmbeddings:
    model = "fake-embeddings"

    def __init__(self) -> None:
        self.calls = 0

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [hashed_bag_of_words(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return hashed_bag_of_words(text)


class FakeChat:
    """Replays scripted completions, streaming each one word by word, and records every call."""

    model = "fake-chat"

    def __init__(self, *completions: ChatCompletion | str) -> None:
        self.script: list[ChatCompletion] = [
            c if isinstance(c, ChatCompletion) else ChatCompletion(text=c) for c in completions
        ]
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None

    def queue(self, *completions: ChatCompletion | str) -> None:
        self.script.extend(
            c if isinstance(c, ChatCompletion) else ChatCompletion(text=c) for c in completions
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        system: str,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[ChatEvent]:
        self.calls.append({"messages": list(messages), "system": system, "tools": list(tools)})
        if self.error is not None:
            raise self.error
        completion = self.script.pop(0) if self.script else ChatCompletion(text="")
        for word in completion.text.split(" "):
            yield TextDelta(word + " ")
        yield completion
