"""Process one stored document: parse → chunk → embed → save chunks → mark ready."""

import asyncio
import uuid
from collections.abc import Sequence
from typing import Any

import structlog
from sqlalchemy import (
    ColumnElement,
    cast,
    delete,
    func,
    insert,
    literal,
    literal_column,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumen.config import Settings
from lumen.db.models import Chunk, Document, DocumentStatus
from lumen.ingestion.chunking import ChunkDraft, chunk_blocks
from lumen.ingestion.language import detect_language
from lumen.ingestion.parsing import ParsingError, parse
from lumen.providers.embeddings import EmbeddingProvider
from lumen.providers.errors import ProviderError
from lumen.storage import FileStorage

log = structlog.get_logger(__name__)

_INSERT_BATCH = 200


def embedding_input(draft: ChunkDraft) -> str:
    """Prefix the heading path so a chunk's vector also carries its section's meaning."""
    if not draft.heading_path:
        return draft.text
    return f"{' > '.join(draft.heading_path)}\n\n{draft.text}"


def tsvector_expression(language: str, headings: str, text: str) -> ColumnElement[Any]:
    """Headings get weight 'A' and body text weight 'B', so title matches rank higher."""
    config = cast(literal(language), REGCONFIG)
    # setweight() takes the internal "char" type, so the weights are untyped SQL literals.
    return func.setweight(func.to_tsvector(config, headings), literal_column("'A'")).op("||")(
        func.setweight(func.to_tsvector(config, text), literal_column("'B'"))
    )


class IngestionService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        storage: FileStorage,
        embedder: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._storage = storage
        self._embedder = embedder
        self._settings = settings

    async def process(self, document_id: uuid.UUID) -> None:
        async with self._sessions() as session:
            document = await session.get(Document, document_id)
            if document is None:
                return  # deleted before we got to it
            document.status = DocumentStatus.PROCESSING
            document.error = None
            doc_type = document.doc_type
            await session.commit()

        logger = log.bind(document_id=str(document_id))
        try:
            data = await asyncio.to_thread(self._storage.read, document_id)
            parsed = await asyncio.to_thread(parse, data, doc_type)
            drafts = chunk_blocks(
                parsed.blocks,
                chunk_size_tokens=self._settings.chunk_size_tokens,
                overlap_tokens=self._settings.chunk_overlap_tokens,
            )
            if not drafts:
                raise ParsingError("The document contains no text.")
            language = detect_language(parsed.text)
            vectors = await self._embedder.embed_documents([embedding_input(d) for d in drafts])
            saved = await self._save_chunks(document_id, drafts, vectors, language)
            if not saved:
                return
            async with self._sessions() as session:
                await session.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(
                        status=DocumentStatus.READY,
                        language=language,
                        page_count=parsed.page_count,
                        chunk_count=len(drafts),
                        embedding_model=self._embedder.model,
                    )
                )
                await session.commit()
            logger.info("document_ready", chunks=len(drafts), language=language)
        except (ParsingError, ProviderError, FileNotFoundError) as exc:
            logger.warning("document_failed", error=str(exc))
            await self._mark_failed(document_id, str(exc) or exc.__class__.__name__)
        except Exception:
            logger.exception("document_failed_unexpectedly")
            await self._mark_failed(document_id, "Unexpected error while processing the document.")

    async def _save_chunks(
        self,
        document_id: uuid.UUID,
        drafts: Sequence[ChunkDraft],
        vectors: Sequence[list[float]],
        language: str,
    ) -> bool:
        async with self._sessions() as session, session.begin():
            # Lock the row so a concurrent delete waits for us (or we see it is gone).
            exists = await session.scalar(
                select(Document.id).where(Document.id == document_id).with_for_update()
            )
            if exists is None:
                return False
            await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            rows = [
                {
                    "id": uuid.uuid7(),
                    "document_id": document_id,
                    "ordinal": ordinal,
                    "text": draft.text,
                    "page": draft.page,
                    "heading_path": list(draft.heading_path),
                    "token_count": draft.token_count,
                    "embedding": vector,
                    "tsv": tsvector_expression(language, " ".join(draft.heading_path), draft.text),
                }
                for ordinal, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
            ]
            for start in range(0, len(rows), _INSERT_BATCH):
                await session.execute(insert(Chunk).values(rows[start : start + _INSERT_BATCH]))
        return True

    async def _mark_failed(self, document_id: uuid.UUID, message: str) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocumentStatus.FAILED, error=message[:1000])
            )
            await session.commit()

    async def pending_documents(self) -> list[uuid.UUID]:
        """Documents interrupted by a restart, oldest first; they are reset to 'pending'."""
        async with self._sessions() as session:
            await session.execute(
                update(Document)
                .where(Document.status == DocumentStatus.PROCESSING)
                .values(status=DocumentStatus.PENDING)
            )
            ids = await session.scalars(
                select(Document.id)
                .where(Document.status == DocumentStatus.PENDING)
                .order_by(Document.created_at)
            )
            await session.commit()
            return list(ids)
