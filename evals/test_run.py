"""Unit tests for the evaluation runner's scoring (no database or model needed).

uv run --project backend pytest evals
"""

import uuid

import pytest

from evals.run import (
    DATASET,
    JUDGE_PROMPT,
    Item,
    evals_database_url,
    first_relevant_rank,
    gate_metrics,
    load_dataset,
    parse_judgement,
    retrieval_metrics,
)
from lumen.retrieval.search import SearchHit


def _hit(filename: str, text: str) -> SearchHit:
    return SearchHit(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename=filename,
        ordinal=0,
        page=None,
        heading_path=(),
        text=text,
        score=0.0,
    )


ITEM = Item(
    id="x",
    language="pt",
    question="?",
    answerable=True,
    expected=[{"filename": "a.pdf", "contains": "3 dias por semana"}],
    reference_answer="3",
)


def test_dataset_is_well_formed() -> None:
    items = load_dataset(DATASET)

    assert len(items) >= 40
    assert len({i.id for i in items}) == len(items)
    assert all(i.expected for i in items if i.answerable)
    assert any(not i.answerable for i in items)


def test_relevance_matches_file_and_text_ignoring_line_breaks() -> None:
    hits = [_hit("b.md", "3 dias por semana"), _hit("a.pdf", "é de 3 dias\npor semana.")]

    assert first_relevant_rank(hits, ITEM) == 2
    assert first_relevant_rank(hits[:1], ITEM) is None


def test_retrieval_metrics() -> None:
    metrics = retrieval_metrics([1, 3, None, 8])

    assert metrics["hit@1"] == 0.25
    assert metrics["hit@3"] == 0.5
    assert metrics["hit@8"] == 0.75
    assert metrics["mrr"] == pytest.approx((1 + 1 / 3 + 1 / 8) / 4)


def test_gate_metrics() -> None:
    rows = [(True, 0.8), (True, 0.4), (False, 0.3), (False, 0.6)]

    metrics = gate_metrics(rows, threshold=0.5)

    assert metrics["accuracy"] == 0.5
    assert metrics["answerable_passed"] == 0.5
    assert metrics["unanswerable_refused"] == 0.5
    assert metrics["lowest_answerable"] == 0.4
    assert metrics["highest_unanswerable"] == 0.6


def test_parse_judgement_is_tolerant() -> None:
    assert parse_judgement('Sure: {"faithfulness": 5, "relevance": 9, "reason": "ok"}') == (
        5,
        5,
        "ok",
    )
    assert parse_judgement("no json here")[0] is None


def test_judge_prompt_formats() -> None:
    prompt = JUDGE_PROMPT.format(question="Q", reference="R", sources="S", answer="A")

    assert '{"faithfulness": <1-5>' in prompt and "ANSWER: A" in prompt


def test_evals_use_their_own_database() -> None:
    url = evals_database_url("postgresql+asyncpg://u:p@localhost:5432/lumen")

    assert url == "postgresql+asyncpg://u:p@localhost:5432/lumen_evals"
