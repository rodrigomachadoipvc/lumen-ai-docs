"""Embedding providers behind one small interface."""

from collections.abc import Sequence
from typing import Protocol

import ollama
import openai

from lumen.config import EMBEDDING_DIMENSIONS, Settings
from lumen.providers.errors import ProviderError


class EmbeddingProvider(Protocol):
    """Turns text into vectors of `EMBEDDING_DIMENSIONS` floats."""

    @property
    def model(self) -> str: ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


def _check_dimensions(vectors: list[list[float]], model: str) -> list[list[float]]:
    for vector in vectors:
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ProviderError(
                f"Embedding model '{model}' returned {len(vector)} dimensions; "
                f"the database expects {EMBEDDING_DIMENSIONS}."
            )
    return vectors


class OllamaEmbeddings:
    def __init__(
        self, *, base_url: str, model: str, query_instruction: str = "", batch_size: int = 16
    ) -> None:
        self._client = ollama.AsyncClient(host=base_url)
        self._base_url = base_url
        self._model = model
        self._query_instruction = query_instruction
        self._batch_size = batch_size

    @property
    def model(self) -> str:
        return self._model

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            try:
                response = await self._client.embed(
                    model=self._model, input=batch, keep_alive="30m"
                )
            except ConnectionError as exc:
                raise ProviderError(
                    f"Could not reach Ollama at {self._base_url}. Is it running?"
                ) from exc
            except ollama.ResponseError as exc:
                hint = f" Run `ollama pull {self._model}`." if exc.status_code == 404 else ""
                raise ProviderError(f"Ollama embedding failed: {exc.error}.{hint}") from exc
            vectors.extend(list(map(float, v)) for v in response.embeddings)
        return _check_dimensions(vectors, self._model)

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([f"{self._query_instruction}{text}"]))[0]


class OpenAIEmbeddings:
    def __init__(self, *, api_key: str, model: str, batch_size: int = 64) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._batch_size = batch_size

    @property
    def model(self) -> str:
        return self._model

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            try:
                response = await self._client.embeddings.create(
                    model=self._model, input=batch, dimensions=EMBEDDING_DIMENSIONS
                )
            except openai.OpenAIError as exc:
                raise ProviderError(f"OpenAI embedding failed: {exc}") from exc
            vectors.extend(item.embedding for item in response.data)
        return _check_dimensions(vectors, self._model)

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        if settings.openai_api_key is None:
            raise ProviderError("LUMEN_OPENAI_API_KEY is required when the provider is 'openai'.")
        return OpenAIEmbeddings(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.embedding_model,
            batch_size=settings.embedding_batch_size,
        )
    return OllamaEmbeddings(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
        query_instruction=settings.embedding_query_instruction,
        batch_size=settings.embedding_batch_size,
    )
