"""Hybrid search: PostgreSQL full-text + pgvector, merged with Reciprocal Rank Fusion.

See docs/adr/0004-hybrid-search.md.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, Text, cast, func, literal, select, text
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from lumen.db.models import Chunk, Document, DocumentStatus
from lumen.ingestion.language import FALLBACK_LANGUAGE, SEARCH_LANGUAGES
from lumen.providers.embeddings import EmbeddingProvider

SearchMode = Literal["hybrid", "vector", "fulltext"]

# Constant from the original RRF paper (Cormack et al., 2009); damps the weight of top ranks.
RRF_K = 60


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    ordinal: int
    page: int | None
    heading_path: tuple[str, ...]
    text: str
    score: float
    # Cosine similarity to the query (1 = same direction); None if not found by vector search.
    similarity: float | None = None
    # PostgreSQL ts_rank_cd; None if not found by full-text search.
    text_rank: float | None = None
    ranks: dict[str, int] = field(default_factory=dict)


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[uuid.UUID]],
    k: int = RRF_K,
    weights: Mapping[str, float] | None = None,
) -> dict[uuid.UUID, float]:
    """score(d) = Σ w_i / (k + rank_i(d)), ranks starting at 1, over every list containing d."""
    scores: dict[uuid.UUID, float] = {}
    for name, ranked_ids in rankings.items():
        weight = (weights or {}).get(name, 1.0)
        for rank, item_id in enumerate(ranked_ids, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (k + rank)
    return scores


def any_word_query(query: str) -> ColumnElement[Any]:
    """A tsquery that matches chunks containing ANY of the query's words, in every language.

    Questions contain words that the answer does not ("how many", "can I"), so the AND semantics
    of plainto_tsquery would find almost nothing. Turning `a & b` into `a | b` fixes that, and
    ts_rank_cd still ranks chunks that match more words higher. Each language stems differently,
    so the per-language queries are OR-ed together; 'simple' keeps exact words and numbers.
    """
    or_queries = [
        cast(
            func.replace(
                cast(func.plainto_tsquery(cast(literal(lang), REGCONFIG), query), Text), "&", "|"
            ),
            TSQUERY,
        )
        for lang in (*SEARCH_LANGUAGES, FALLBACK_LANGUAGE)
    ]
    combined: ColumnElement[Any] = or_queries[0]
    for or_query in or_queries[1:]:
        combined = combined.op("||")(or_query)
    return combined


def _filtered(statement: Select[Any], document_ids: Sequence[uuid.UUID] | None) -> Select[Any]:
    statement = statement.join(Document, Document.id == Chunk.document_id).where(
        Document.status == DocumentStatus.READY
    )
    if document_ids:
        statement = statement.where(Chunk.document_id.in_(document_ids))
    return statement


async def full_text_search(
    session: AsyncSession, query: str, *, limit: int, document_ids: Sequence[uuid.UUID] | None
) -> list[tuple[uuid.UUID, float]]:
    tsquery = any_word_query(query)
    rank = func.ts_rank_cd(Chunk.tsv, tsquery).label("rank")
    statement = _filtered(
        select(Chunk.id, rank).where(Chunk.tsv.op("@@")(tsquery)), document_ids
    ).order_by(rank.desc(), Chunk.id)
    rows = await session.execute(statement.limit(limit))
    return [(row.id, float(row.rank)) for row in rows]


async def vector_search(
    session: AsyncSession,
    embedding: list[float],
    *,
    limit: int,
    document_ids: Sequence[uuid.UUID] | None,
) -> list[tuple[uuid.UUID, float]]:
    # Keep scanning the HNSW index until enough rows pass the filters (pgvector >= 0.8).
    await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    distance = Chunk.embedding.cosine_distance(embedding).label("distance")
    statement = _filtered(select(Chunk.id, distance), document_ids).order_by(distance)
    rows = await session.execute(statement.limit(limit))
    return [(row.id, 1.0 - float(row.distance)) for row in rows]


async def search(
    session: AsyncSession,
    embedder: EmbeddingProvider,
    query: str,
    *,
    limit: int = 8,
    mode: SearchMode = "hybrid",
    document_ids: Sequence[uuid.UUID] | None = None,
    candidates: int = 30,
) -> list[SearchHit]:
    """Return the `limit` best chunks for `query`, best first."""
    rankings: dict[str, list[uuid.UUID]] = {}
    similarities: dict[uuid.UUID, float] = {}
    text_ranks: dict[uuid.UUID, float] = {}

    if mode in ("hybrid", "fulltext"):
        fts = await full_text_search(session, query, limit=candidates, document_ids=document_ids)
        rankings["fulltext"] = [chunk_id for chunk_id, _ in fts]
        text_ranks = dict(fts)
    if mode in ("hybrid", "vector"):
        embedding = await embedder.embed_query(query)
        vec = await vector_search(session, embedding, limit=candidates, document_ids=document_ids)
        rankings["vector"] = [chunk_id for chunk_id, _ in vec]
        similarities = dict(vec)

    # Equal weights: the evals showed down-weighting full-text did not help (docs/evals.md).
    fused = reciprocal_rank_fusion(rankings)
    best = sorted(fused, key=lambda chunk_id: (-fused[chunk_id], str(chunk_id)))[:limit]
    if not best:
        return []

    rows = await session.execute(
        select(Chunk, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_(best))
    )
    by_id = {chunk.id: (chunk, filename) for chunk, filename in rows}
    hits: list[SearchHit] = []
    for chunk_id in best:
        chunk, filename = by_id[chunk_id]
        hits.append(
            SearchHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                ordinal=chunk.ordinal,
                page=chunk.page,
                heading_path=tuple(chunk.heading_path),
                text=chunk.text,
                score=fused[chunk_id],
                similarity=similarities.get(chunk_id),
                text_rank=text_ranks.get(chunk_id),
                ranks={
                    name: ranked.index(chunk_id) + 1
                    for name, ranked in rankings.items()
                    if chunk_id in ranked
                },
            )
        )
    return hits
