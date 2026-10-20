"""The tools the agent can call. Every passage a tool returns gets a global number for citing."""

import contextlib
import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumen.answers.citations import source_payload
from lumen.answers.prompts import format_source
from lumen.db.models import Chunk, Document, DocumentStatus
from lumen.providers.chat import ToolSpec
from lumen.providers.embeddings import EmbeddingProvider
from lumen.retrieval.search import SearchHit, search

MAX_SECTION_CHUNKS = 6
_FILLER_WORDS = frozenset("de do da dos das the of and e a o pdf md txt markdown".split())


def _name_words(name: str) -> frozenset[str]:
    """Meaningful words of a document name: lower-cased, without extension or filler words."""
    words = re.findall(r"[^\W_]+", name.lower())
    return frozenset(w for w in words if w not in _FILLER_WORDS)


class ToolError(Exception):
    """A problem the model can fix (bad arguments, unknown document). Sent back as the result."""


@dataclass
class SourceRegistry:
    """Numbers passages in the order the agent first sees them, so [n] is stable across steps."""

    hits: list[SearchHit] = field(default_factory=list)
    _numbers: dict[uuid.UUID, int] = field(default_factory=dict)

    def add(self, hit: SearchHit) -> int:
        if hit.chunk_id not in self._numbers:
            self.hits.append(hit)
            self._numbers[hit.chunk_id] = len(self.hits)
        return self._numbers[hit.chunk_id]

    def payloads(self) -> list[dict[str, Any]]:
        return [source_payload(n, hit) for n, hit in enumerate(self.hits, start=1)]


@dataclass(frozen=True)
class ToolResult:
    content: str
    summary: str
    source_numbers: tuple[int, ...] = ()


# --- Argument schemas -------------------------------------------------------------------


class SearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    documents: list[str] | None = Field(default=None, max_length=10)


class SectionArgs(BaseModel):
    document: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    heading: str | None = Field(default=None, min_length=1, max_length=200)


class CompareArgs(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    documents: list[str] = Field(min_length=2, max_length=4)


class ListArgs(BaseModel):
    pass


DOCUMENT_HINT = "A document's filename (as shown by list_documents) or its id."

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "search_documents",
        "Hybrid keyword + semantic search over the documents. Returns numbered passages with "
        "document, page and section. Optionally restrict to some documents.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for."},
                "documents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"Optional. {DOCUMENT_HINT}",
                },
            },
            "required": ["query"],
        },
    ),
    ToolSpec(
        "get_document_section",
        "Read a part of one document: all passages on a page, or under a heading. Use it to see "
        "the full context around a search result.",
        {
            "type": "object",
            "properties": {
                "document": {"type": "string", "description": DOCUMENT_HINT},
                "page": {"type": "integer", "description": "1-based page number (PDFs)."},
                "heading": {"type": "string", "description": "Text contained in a heading."},
            },
            "required": ["document"],
        },
    ),
    ToolSpec(
        "compare_documents",
        "Search the same question separately in 2 to 4 documents, to compare what each says.",
        {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "documents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"2 to 4 documents. {DOCUMENT_HINT}",
                },
            },
            "required": ["question", "documents"],
        },
    ),
    ToolSpec(
        "list_documents",
        "List the available documents with their type, pages and language.",
        {"type": "object", "properties": {}},
    ),
)


# --- Implementation ---------------------------------------------------------------------


class DocumentTools:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: EmbeddingProvider,
        registry: SourceRegistry,
        allowed_documents: Sequence[uuid.UUID] | None = None,
        passages_per_search: int = 5,
    ) -> None:
        self._sessions = session_factory
        self._embedder = embedder
        self._registry = registry
        self._allowed = list(allowed_documents) if allowed_documents else None
        self._limit = passages_per_search
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[ToolResult]]] = {
            "search_documents": self._search,
            "get_document_section": self._section,
            "compare_documents": self._compare,
            "list_documents": self._list,
        }

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        handler = self._handlers.get(name)
        if handler is None:
            raise ToolError(f"Unknown tool '{name}'. Available: {', '.join(self._handlers)}.")
        try:
            return await handler(arguments)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in exc.errors()
            )
            raise ToolError(f"Invalid arguments for {name}: {problems}") from exc

    def _render(self, hits: Sequence[SearchHit]) -> tuple[str, tuple[int, ...]]:
        numbers = tuple(self._registry.add(hit) for hit in hits)
        blocks = [format_source(n, hit) for n, hit in zip(numbers, hits, strict=True)]
        return "\n\n".join(blocks), numbers

    async def _resolve(self, session: AsyncSession, references: Sequence[str]) -> list[Document]:
        """Accept ids or filenames (exact or partial, case-insensitive) for robustness."""
        documents: list[Document] = []
        for reference in references:
            reference = reference.strip()
            conditions = [func.lower(Document.filename) == reference.lower()]
            with contextlib.suppress(ValueError):
                conditions.append(Document.id == uuid.UUID(reference))
            statement = select(Document).where(Document.status == DocumentStatus.READY)
            if self._allowed:
                statement = statement.where(Document.id.in_(self._allowed))
            document = await session.scalar(statement.where(or_(*conditions)))
            if document is None:
                # "regulamento de teletrabalho" should find "regulamento-teletrabalho.pdf".
                wanted = _name_words(reference)
                candidates = list(await session.scalars(statement))
                matches = [d for d in candidates if wanted and wanted <= _name_words(d.filename)]
                document = matches[0] if len(matches) == 1 else None
            if document is None:
                raise ToolError(
                    f"No document matches '{reference}'. Call list_documents to see the names."
                )
            if document not in documents:
                documents.append(document)
        return documents

    async def _search(self, raw: dict[str, Any]) -> ToolResult:
        args = SearchArgs.model_validate(raw)
        async with self._sessions() as session:
            scope = self._allowed
            if args.documents:
                scope = [d.id for d in await self._resolve(session, args.documents)]
            hits = await search(
                session, self._embedder, args.query, limit=self._limit, document_ids=scope
            )
        if not hits:
            return ToolResult("No passages found.", f'"{args.query}": nothing found')
        content, numbers = self._render(hits)
        return ToolResult(content, f'"{args.query}": {len(hits)} passages', numbers)

    async def _section(self, raw: dict[str, Any]) -> ToolResult:
        args = SectionArgs.model_validate(raw)
        if args.page is None and args.heading is None:
            raise ToolError("Give a page or a heading.")
        async with self._sessions() as session:
            (document,) = await self._resolve(session, [args.document])
            statement = select(Chunk).where(Chunk.document_id == document.id)
            if args.page is not None:
                statement = statement.where(Chunk.page == args.page)
            if args.heading is not None:
                headings = func.array_to_string(Chunk.heading_path, " > ")
                statement = statement.where(headings.ilike(f"%{args.heading}%"))
            chunks = list(
                await session.scalars(statement.order_by(Chunk.ordinal).limit(MAX_SECTION_CHUNKS))
            )
        where = f"page {args.page}" if args.page else f'"{args.heading}"'
        if not chunks:
            return ToolResult(
                f"{document.filename} has no passages for {where}.",
                f"{document.filename}, {where}: nothing found",
            )
        hits = [
            SearchHit(
                chunk_id=c.id,
                document_id=c.document_id,
                filename=document.filename,
                ordinal=c.ordinal,
                page=c.page,
                heading_path=tuple(c.heading_path),
                text=c.text,
                score=0.0,
            )
            for c in chunks
        ]
        content, numbers = self._render(hits)
        return ToolResult(content, f"{document.filename}, {where}: {len(hits)} passages", numbers)

    async def _compare(self, raw: dict[str, Any]) -> ToolResult:
        args = CompareArgs.model_validate(raw)
        parts: list[str] = []
        numbers: list[int] = []
        async with self._sessions() as session:
            documents = await self._resolve(session, args.documents)
            if len(documents) < 2:
                raise ToolError("compare_documents needs at least two different documents.")
            for document in documents:
                hits = await search(
                    session, self._embedder, args.question, limit=3, document_ids=[document.id]
                )
                content, found = self._render(hits)
                numbers.extend(found)
                parts.append(
                    f'<document name="{document.filename}">\n'
                    f"{content or 'No relevant passages.'}\n</document>"
                )
        names = ", ".join(d.filename for d in documents)
        return ToolResult("\n\n".join(parts), f"compared {names}", tuple(numbers))

    async def _list(self, raw: dict[str, Any]) -> ToolResult:
        ListArgs.model_validate(raw)
        async with self._sessions() as session:
            statement = select(Document).where(Document.status == DocumentStatus.READY)
            if self._allowed:
                statement = statement.where(Document.id.in_(self._allowed))
            documents = list(await session.scalars(statement.order_by(Document.filename)))
        if not documents:
            return ToolResult("There are no documents yet.", "no documents")
        lines = [
            f"- {d.filename} (id {d.id}; {d.doc_type.value}"
            + (f", {d.page_count} pages" if d.page_count else "")
            + f", {d.language or 'unknown language'})"
            for d in documents
        ]
        return ToolResult("\n".join(lines), f"{len(documents)} documents")
