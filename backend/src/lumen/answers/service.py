"""Answer one question from the documents: retrieve → check evidence → stream → cite."""

import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumen.answers.citations import citations_for, source_payload, strip_invalid_markers
from lumen.answers.prompts import NOT_FOUND, SYSTEM_PROMPT, build_question_prompt
from lumen.config import Settings
from lumen.ingestion.language import detect_language
from lumen.observability import LLMTracer, usage_details
from lumen.providers.chat import ChatCompletion, ChatMessage, ChatProvider, TextDelta
from lumen.providers.embeddings import EmbeddingProvider
from lumen.retrieval.search import SearchHit, search


@dataclass(frozen=True)
class SourcesEvent:
    sources: list[dict[str, Any]]


@dataclass(frozen=True)
class DeltaEvent:
    text: str


@dataclass(frozen=True)
class StepEvent:
    """One agent tool call and a short summary of its result."""

    step: dict[str, Any]


@dataclass(frozen=True)
class DoneEvent:
    answer: str
    citations: list[dict[str, Any]]
    grounded: bool
    model: str | None
    sources: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ResetEvent:
    """Text streamed during an agent step that turned out to be a tool call; discard it."""


AnswerEvent = SourcesEvent | DeltaEvent | StepEvent | ResetEvent | DoneEvent


def not_found_message(question: str) -> str:
    return NOT_FOUND.get(detect_language(question), NOT_FOUND["english"])


def retrieval_query(question: str, history: Sequence[ChatMessage]) -> str:
    """Follow-ups like "and on Fridays?" only make sense with the previous question attached."""
    previous = next((m.content for m in reversed(history) if m.role == "user"), None)
    return f"{previous}\n{question}" if previous else question


def has_enough_evidence(hits: Sequence[SearchHit], min_similarity: float) -> bool:
    best = max((h.similarity for h in hits if h.similarity is not None), default=0.0)
    return best >= min_similarity


def _hit_summary(hit: SearchHit) -> dict[str, Any]:
    return {
        "filename": hit.filename,
        "page": hit.page,
        "section": " > ".join(hit.heading_path),
        "similarity": hit.similarity,
        "ranks": hit.ranks,
    }


def _as_dicts(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


class AnswerService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: EmbeddingProvider,
        chat: ChatProvider,
        settings: Settings,
        tracer: LLMTracer | None = None,
    ) -> None:
        self._sessions = session_factory
        self._embedder = embedder
        self._chat = chat
        self._settings = settings
        self._tracer = tracer or LLMTracer()

    async def answer(
        self,
        question: str,
        *,
        history: Sequence[ChatMessage] = (),
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> AsyncIterator[AnswerEvent]:
        query = retrieval_query(question, history)
        with self._tracer.observe("retrieval", as_type="retriever", input=query) as observation:
            async with self._sessions() as session:
                hits = await search(
                    session,
                    self._embedder,
                    query,
                    limit=self._settings.answer_passages,
                    document_ids=document_ids,
                )
            observation.update(output=[_hit_summary(h) for h in hits])

        if not hits or not has_enough_evidence(hits, self._settings.min_similarity):
            message = not_found_message(question)
            yield SourcesEvent([])
            yield DeltaEvent(message)
            yield DoneEvent(answer=message, citations=[], grounded=False, model=None)
            return

        sources = [source_payload(n, hit) for n, hit in enumerate(hits, start=1)]
        yield SourcesEvent(sources)

        messages = [*history, ChatMessage("user", build_question_prompt(question, hits))]
        final_text = ""
        with self._tracer.observe(
            "answer",
            as_type="generation",
            model=self._chat.model,
            input=[{"role": "system", "content": SYSTEM_PROMPT}, *_as_dicts(messages)],
        ) as generation:
            async for event in self._chat.stream(messages, system=SYSTEM_PROMPT):
                if isinstance(event, TextDelta):
                    yield DeltaEvent(event.text)
                elif isinstance(event, ChatCompletion):
                    final_text = event.text
                    generation.update(output=event.text, usage_details=usage_details(event.usage))

        answer = strip_invalid_markers(final_text, len(hits)) or not_found_message(question)
        citations = citations_for(answer, hits)
        yield DoneEvent(
            answer=answer,
            citations=citations,
            grounded=bool(citations),
            model=self._chat.model,
            sources=sources,
        )

    def answer_turn(
        self,
        question: str,
        history: Sequence[ChatMessage],
        document_ids: Sequence[uuid.UUID] | None,
    ) -> AsyncIterator[AnswerEvent]:
        """`answer()` with the positional signature the turn runner expects."""
        return self.answer(question, history=history, document_ids=document_ids)
