import uuid

import pytest
from httpx2 import AsyncClient
from sqlalchemy import select

from lumen.container import Container
from lumen.db.models import Document
from lumen.retrieval.search import RRF_K, reciprocal_rank_fusion, search
from lumen.seed import DEFAULT_SAMPLES, sample_files, seed


def test_rrf_rewards_items_found_by_both_rankers() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    scores = reciprocal_rank_fusion({"fulltext": [a, b], "vector": [c, b]})

    assert scores[b] == pytest.approx(2 / (RRF_K + 2))
    assert scores[a] == pytest.approx(1 / (RRF_K + 1))
    assert max(scores, key=scores.__getitem__) == b


def test_rrf_weights_scale_each_ranking() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()

    scores = reciprocal_rank_fusion({"fulltext": [a], "vector": [b]}, weights={"fulltext": 0.5})

    assert scores[a] == pytest.approx(0.5 / (RRF_K + 1))
    assert scores[b] == pytest.approx(1 / (RRF_K + 1))


def test_rrf_of_nothing_is_empty() -> None:
    assert reciprocal_rank_fusion({"fulltext": [], "vector": []}) == {}


@pytest.fixture
async def corpus(container: Container) -> dict[str, uuid.UUID]:
    """The demo documents, processed with the fake embedder. Maps filename -> document id."""
    await seed(container, sample_files(DEFAULT_SAMPLES))
    async with container.sessions() as session:
        rows = await session.execute(select(Document.filename, Document.id))
        return {filename: document_id for filename, document_id in rows}


async def test_full_text_finds_exact_terms(
    container: Container, corpus: dict[str, uuid.UUID]
) -> None:
    async with container.sessions() as session:
        hits = await search(session, container.embedder, "Olympus Mons", mode="fulltext")

    assert hits[0].filename == "solar-system-notes.txt"
    assert "Olympus Mons" in hits[0].text
    assert hits[0].text_rank is not None and hits[0].similarity is None


async def test_full_text_matches_questions_with_extra_words(
    container: Container, corpus: dict[str, uuid.UUID]
) -> None:
    question = "Qual é o valor da compensação mensal por despesas de eletricidade?"

    async with container.sessions() as session:
        hits = await search(session, container.embedder, question, mode="fulltext", limit=3)

    assert any("40 euros" in hit.text for hit in hits)


async def test_vector_search_returns_similarity(
    container: Container, corpus: dict[str, uuid.UUID]
) -> None:
    async with container.sessions() as session:
        hits = await search(
            session, container.embedder, "Great Red Spot storm on Jupiter", mode="vector"
        )

    assert "Great Red Spot" in hits[0].text
    assert hits[0].similarity is not None and 0 < hits[0].similarity <= 1
    assert hits[0].ranks == {"vector": 1}


async def test_hybrid_combines_both_rankings(
    container: Container, corpus: dict[str, uuid.UUID]
) -> None:
    async with container.sessions() as session:
        hits = await search(session, container.embedder, "birthday leave day off")

    top = hits[0]
    assert top.filename == "employee-handbook.md"
    assert top.heading_path[-1] == "Birthday leave"
    assert set(top.ranks) == {"fulltext", "vector"}
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


async def test_filter_by_document(container: Container, corpus: dict[str, uuid.UUID]) -> None:
    only = corpus["politica-privacidade.md"]

    async with container.sessions() as session:
        hits = await search(session, container.embedder, "dados", document_ids=[only], limit=20)

    assert hits
    assert {h.document_id for h in hits} == {only}


async def test_pdf_hits_carry_page_and_heading(
    container: Container, corpus: dict[str, uuid.UUID]
) -> None:
    async with container.sessions() as session:
        hits = await search(
            session, container.embedder, "limite máximo de dias de teletrabalho por semana"
        )

    article_7 = next(h for h in hits if h.heading_path and "Artigo 7" in h.heading_path[-1])
    assert article_7.filename == "regulamento-teletrabalho.pdf"
    assert article_7.page == 3


async def test_stopword_only_query_returns_nothing_from_full_text(
    container: Container, corpus: dict[str, uuid.UUID]
) -> None:
    async with container.sessions() as session:
        hits = await search(session, container.embedder, "the of and", mode="fulltext")

    assert hits == []


async def test_search_endpoint(client: AsyncClient, corpus: dict[str, uuid.UUID]) -> None:
    response = await client.post("/search", json={"query": "Pluto dwarf planet", "limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "hybrid"
    assert len(body["hits"]) == 2
    first = body["hits"][0]
    assert first["filename"] == "solar-system-notes.txt"
    assert set(first) >= {"chunk_id", "document_id", "page", "heading_path", "text", "score"}


async def test_search_endpoint_validates_input(client: AsyncClient) -> None:
    empty = await client.post("/search", json={"query": ""})
    too_many = await client.post("/search", json={"query": "x", "limit": 500})

    assert empty.status_code == 422
    assert too_many.status_code == 422
    assert empty.json()["error"]["code"] == "validation_error"
