"""Measure Lumen's quality on the golden dataset in evals/dataset.jsonl.

From the repository root:

    uv run --project backend python -m evals.run              # retrieval + "I don't know" gate
    uv run --project backend python -m evals.run --answers    # + answers judged by an LLM (slow)

It uses a separate database (`<your database>_evals`), loads data/samples into it, and writes a
JSON report to evals/results/. See docs/evals.md.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from lumen.answers.service import DoneEvent
from lumen.config import Settings, get_settings
from lumen.container import Container
from lumen.logging_config import configure_logging
from lumen.providers.chat import ChatCompletion, ChatMessage
from lumen.retrieval.search import SearchHit, SearchMode, search
from lumen.seed import DEFAULT_SAMPLES, sample_files, seed

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "dataset.jsonl"
RESULTS = ROOT / "evals" / "results"
KS = (1, 3, 5, 8)
MODES: tuple[SearchMode, ...] = ("hybrid", "vector", "fulltext")

JUDGE_PROMPT = """\
You grade an answer produced by a document assistant. Score it with this fixed rubric.

faithfulness (1-5): is every claim in the ANSWER supported by the SOURCES?
  5 = fully supported; 3 = mostly, one unsupported detail; 1 = mainly unsupported or invented.
relevance (1-5): does the ANSWER address the QUESTION, compared with the REFERENCE answer?
  5 = complete and correct; 3 = partly correct or incomplete; 1 = wrong or off-topic.

Reply with JSON only: {{"faithfulness": <1-5>, "relevance": <1-5>, "reason": "<one sentence>"}}

QUESTION: {question}
REFERENCE: {reference}
SOURCES:
{sources}

ANSWER: {answer}
"""


@dataclass
class Item:
    id: str
    language: str
    question: str
    answerable: bool
    expected: list[dict[str, str]]
    reference_answer: str | None


@dataclass
class RetrievalResult:
    id: str
    mode: str
    rank: int | None  # 1-based position of the first relevant passage, None if not found


@dataclass
class AnswerResult:
    id: str
    answerable: bool
    answer: str
    grounded: bool
    correct_refusal: bool | None = None
    faithfulness: int | None = None
    relevance: int | None = None
    reason: str = ""
    seconds: float = 0.0


@dataclass
class Report:
    created_at: str
    settings: dict[str, Any]
    retrieval: dict[str, dict[str, float]] = field(default_factory=dict)
    gate: dict[str, float] = field(default_factory=dict)
    answers: dict[str, float] = field(default_factory=dict)
    misses: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def load_dataset(path: Path = DATASET) -> list[Item]:
    with path.open(encoding="utf-8") as handle:
        return [Item(**json.loads(line)) for line in handle if line.strip()]


def is_relevant(hit: SearchHit, item: Item) -> bool:
    text_ = " ".join(hit.text.split())
    return any(
        hit.filename == e["filename"] and " ".join(e["contains"].split()) in text_
        for e in item.expected
    )


def first_relevant_rank(hits: list[SearchHit], item: Item) -> int | None:
    return next((rank for rank, hit in enumerate(hits, start=1) if is_relevant(hit, item)), None)


def retrieval_metrics(ranks: list[int | None]) -> dict[str, float]:
    """hit@k = share of questions with a relevant passage in the top k; MRR = mean of 1/rank."""
    n = len(ranks) or 1
    metrics = {f"hit@{k}": sum(r is not None and r <= k for r in ranks) / n for k in KS}
    metrics["mrr"] = sum(1 / r for r in ranks if r is not None) / n
    return metrics


def gate_metrics(rows: list[tuple[bool, float]], threshold: float) -> dict[str, float]:
    """rows = (answerable, best similarity). The gate refuses when similarity < threshold."""
    refused_unanswerable = sum(not a and s < threshold for a, s in rows)
    passed_answerable = sum(a and s >= threshold for a, s in rows)
    unanswerable = sum(not a for a, _ in rows) or 1
    answerable = sum(a for a, _ in rows) or 1
    return {
        "threshold": threshold,
        "accuracy": (refused_unanswerable + passed_answerable) / (len(rows) or 1),
        "unanswerable_refused": refused_unanswerable / unanswerable,
        "answerable_passed": passed_answerable / answerable,
        "lowest_answerable": min((s for a, s in rows if a), default=0.0),
        "highest_unanswerable": max((s for a, s in rows if not a), default=0.0),
    }


def _score(value: Any) -> int:
    return max(1, min(5, int(value)))


def parse_judgement(text_: str) -> tuple[int | None, int | None, str]:
    start, end = text_.find("{"), text_.rfind("}")
    try:
        data = json.loads(text_[start : end + 1])
        return _score(data["faithfulness"]), _score(data["relevance"]), str(data.get("reason", ""))
    except ValueError, KeyError, TypeError:
        return None, None, f"unparseable judgement: {text_[:120]}"


def evals_database_url(base: str) -> str:
    url = make_url(base)
    return url.set(database=f"{url.database}_evals").render_as_string(hide_password=False)


async def prepare_database(settings: Settings) -> None:
    """Create the evals database if needed, migrate it and load the demo corpus."""
    url = make_url(settings.database_url)
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    await admin.dispose()

    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    config.attributes["configure_logger"] = False
    await asyncio.to_thread(command.upgrade, config, "head")


async def run_retrieval(container: Container, items: list[Item], report: Report) -> None:
    answerable = [i for i in items if i.answerable]
    details: list[dict[str, Any]] = []
    async with container.sessions() as session:
        for mode in MODES:
            ranks: list[int | None] = []
            for item in answerable:
                hits = await search(
                    session, container.embedder, item.question, limit=max(KS), mode=mode
                )
                rank = first_relevant_rank(hits, item)
                ranks.append(rank)
                details.append(asdict(RetrievalResult(item.id, mode, rank)))
                if mode == "hybrid" and (rank is None or rank > 3):
                    report.misses.append(
                        {
                            "id": item.id,
                            "question": item.question,
                            "rank": rank,
                            "top": [
                                f"{h.filename} p{h.page} {' > '.join(h.heading_path)[-40:]}"
                                for h in hits[:3]
                            ],
                        }
                    )
            report.retrieval[mode] = retrieval_metrics(ranks)

        rows: list[tuple[bool, float]] = []
        for item in items:
            hits = await search(session, container.embedder, item.question, limit=1, mode="vector")
            rows.append((item.answerable, hits[0].similarity or 0.0 if hits else 0.0))
    report.gate = gate_metrics(rows, container.settings.min_similarity)
    report.details["retrieval"] = details


async def run_answers(container: Container, items: list[Item], report: Report) -> None:
    results: list[AnswerResult] = []
    for number, item in enumerate(items, start=1):
        print(f"  answering {number}/{len(items)}: {item.id}", flush=True)
        started = time.monotonic()
        done: DoneEvent | None = None
        async for event in container.answers.answer(item.question):
            if isinstance(event, DoneEvent):
                done = event
        seconds = time.monotonic() - started
        if done is None:
            continue
        result = AnswerResult(item.id, item.answerable, done.answer, done.grounded, seconds=seconds)
        if not item.answerable:
            result.correct_refusal = not done.grounded
        elif done.grounded:
            sources = "\n\n".join(
                f"[{s['number']}] {s['filename']} p{s['page']}: {s['text']}" for s in done.sources
            )
            prompt = JUDGE_PROMPT.format(
                question=item.question,
                reference=item.reference_answer,
                sources=sources,
                answer=done.answer,
            )
            judgement = ""
            async for chunk in container.chat.stream(
                [ChatMessage("user", prompt)], system="You are a strict evaluator."
            ):
                if isinstance(chunk, ChatCompletion):
                    judgement = chunk.text
            result.faithfulness, result.relevance, result.reason = parse_judgement(judgement)
        results.append(result)

    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]
    judged = [r for r in answerable if r.faithfulness is not None]
    report.answers = {
        "answered_with_citations": sum(r.grounded for r in answerable) / (len(answerable) or 1),
        "correct_refusals": sum(bool(r.correct_refusal) for r in unanswerable)
        / (len(unanswerable) or 1),
        "faithfulness": statistics.fmean(r.faithfulness or 0 for r in judged) if judged else 0.0,
        "relevance": statistics.fmean(r.relevance or 0 for r in judged) if judged else 0.0,
        "median_seconds": statistics.median(r.seconds for r in results) if results else 0.0,
    }
    report.details["answers"] = [asdict(r) for r in results]


def print_report(report: Report) -> None:
    print("\nRetrieval (answerable questions)")
    print(f"  {'mode':<9}" + "".join(f"{f'hit@{k}':>8}" for k in KS) + f"{'MRR':>8}")
    for mode, metrics in report.retrieval.items():
        values = "".join(f"{metrics[f'hit@{k}']:>8.2f}" for k in KS)
        print(f"  {mode:<9}{values}{metrics['mrr']:>8.2f}")
    gate = report.gate
    print(f'\n"I don\'t know" gate (similarity < {gate["threshold"]})')
    print(
        f"  accuracy {gate['accuracy']:.2f} | unanswerable refused "
        f"{gate['unanswerable_refused']:.2f} | answerable passed {gate['answerable_passed']:.2f}"
    )
    print(
        f"  lowest answerable {gate['lowest_answerable']:.3f} | highest unanswerable "
        f"{gate['highest_unanswerable']:.3f}"
    )
    if report.answers:
        a = report.answers
        print("\nAnswers")
        print(
            f"  cited {a['answered_with_citations']:.2f} | correct refusals "
            f"{a['correct_refusals']:.2f} | faithfulness {a['faithfulness']:.2f}/5 | "
            f"relevance {a['relevance']:.2f}/5 | median {a['median_seconds']:.1f} s"
        )
    if report.misses:
        print("\nHybrid misses (relevant passage not in the top 3)")
        for miss in report.misses:
            top = miss["top"][0] if miss["top"] else "-"
            print(f"  {miss['id']}: rank {miss['rank']} - top: {top}")


async def main_async(args: argparse.Namespace) -> Report:
    base = get_settings()
    settings = base.model_copy(update={"database_url": evals_database_url(base.database_url)})
    await prepare_database(settings)
    container = Container.build(settings)
    try:
        await seed(container, sample_files(DEFAULT_SAMPLES))
        items = load_dataset()
        report = Report(
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            settings={
                "embedding_model": settings.embedding_model,
                "chat_model": container.chat.model,
                "chunk_size_tokens": settings.chunk_size_tokens,
                "min_similarity": settings.min_similarity,
                "questions": len(items),
            },
        )
        await run_retrieval(container, items, report)
        if args.answers:
            print("\nAnswering every question (this calls the chat model)…")
            await run_answers(container, items, report)
        return report
    finally:
        await container.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Lumen's evaluations.")
    parser.add_argument("--answers", action="store_true", help="also judge answers (slow)")
    parser.add_argument("--output", type=Path, help="where to write the JSON report")
    parser.add_argument("--min-hit-at-5", type=float, default=None, help="fail below this")
    args = parser.parse_args()

    configure_logging("WARNING", json=False)
    report = asyncio.run(main_async(args))
    print_report(report)

    output = args.output or RESULTS / f"{report.created_at.replace(':', '-')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport written to {output}")

    hit5 = report.retrieval["hybrid"]["hit@5"]
    if args.min_hit_at_5 is not None and hit5 < args.min_hit_at_5:
        sys.exit(f"hybrid hit@5 {hit5:.2f} is below the required {args.min_hit_at_5:.2f}")


if __name__ == "__main__":
    main()
