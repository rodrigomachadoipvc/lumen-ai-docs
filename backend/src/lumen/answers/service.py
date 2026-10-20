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


AnswerEvent = SourcesEvent | DeltaEvent | StepEvent | DoneEvent


def not_found_message(question: str) -> str:
    return NOT_FOUND.get(detect_language(question), NOT_FOUND["english"])


def retrieval_query(question: str, history: Sequence[ChatMessage]) -> str:
    """Follow-ups like "and on Fridays?" only make sense with the previous question attached."""
    previous = next((m.content for m in reversed(history) if m.role == "user"), None)
    return f"{previous}\n{question}" if previous else question


def has_enough_evidence(hits: Sequence[SearchHit], min_similarity: float) -> bool:
    best = max((h.similarity for h in hits if h.similarity is not None), default=0.0)
    return best >= min_similarity


class AnswerService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: EmbeddingProvider,
        chat: ChatProvider,
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._embedder = embedder
        self._chat = chat
        self._settings = settings

    async def answer(
        self,
        question: str,
        *,
        history: Sequence[ChatMessage] = (),
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> AsyncIterator[AnswerEvent]:
        async with self._sessions() as session:
            hits = await search(
                session,
                self._embedder,
                retrieval_query(question, history),
                limit=self._settings.answer_passages,
                document_ids=document_ids,
            )

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
        async for event in self._chat.stream(messages, system=SYSTEM_PROMPT):
            if isinstance(event, TextDelta):
                yield DeltaEvent(event.text)
            elif isinstance(event, ChatCompletion):
                final_text = event.text

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
