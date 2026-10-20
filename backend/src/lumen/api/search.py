"""Search the indexed documents."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from lumen.api.deps import ContainerDep, SessionDep
from lumen.retrieval.search import SearchHit, SearchMode, search

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=50)
    mode: SearchMode = "hybrid"
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class SearchHitOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page: int | None
    heading_path: list[str]
    text: str
    score: float
    similarity: float | None
    text_rank: float | None
    ranks: dict[str, int]

    @classmethod
    def from_hit(cls, hit: SearchHit) -> SearchHitOut:
        return cls(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            filename=hit.filename,
            page=hit.page,
            heading_path=list(hit.heading_path),
            text=hit.text,
            score=hit.score,
            similarity=hit.similarity,
            text_rank=hit.text_rank,
            ranks=hit.ranks,
        )


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    hits: list[SearchHitOut]


@router.post("/search")
async def search_documents(
    request: SearchRequest, session: SessionDep, container: ContainerDep
) -> SearchResponse:
    """Hybrid search (full-text + vector, fused with RRF) over ready documents."""
    query = request.query.strip()
    hits = await search(
        session,
        container.embedder,
        query,
        limit=request.limit,
        mode=request.mode,
        document_ids=request.document_ids,
    )
    return SearchResponse(
        query=query, mode=request.mode, hits=[SearchHitOut.from_hit(h) for h in hits]
    )
