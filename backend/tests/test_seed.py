import pytest
from sqlalchemy import select

from lumen.container import Container
from lumen.db.models import Chunk, Document, DocumentStatus
from lumen.seed import DEFAULT_SAMPLES, sample_files, seed

SAMPLE_FILES = sample_files(DEFAULT_SAMPLES)


async def test_demo_corpus_loads_and_is_idempotent(
    container: Container, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await seed(container, SAMPLE_FILES) == 0
    assert await seed(container, SAMPLE_FILES) == 0  # second run skips everything
    assert capsys.readouterr().out.count("skip") == len(SAMPLE_FILES)

    async with container.sessions() as session:
        documents = (await session.scalars(select(Document))).all()
        pdf_chunks = (
            await session.scalars(
                select(Chunk)
                .join(Document)
                .where(Document.filename == "regulamento-teletrabalho.pdf")
                .order_by(Chunk.ordinal)
            )
        ).all()

    assert len(documents) == len(SAMPLE_FILES)
    assert all(d.status is DocumentStatus.READY for d in documents)
    # Article 7 of the regulation is on page 3, under chapter II.
    article_7 = next(
        c for c in pdf_chunks if c.heading_path[-1:] and c.heading_path[-1].startswith("Artigo 7")
    )
    assert article_7.page == 3
    assert article_7.heading_path[0].startswith("Capítulo II")
    assert "3 dias por semana" in article_7.text


def test_sample_files_skip_the_readme() -> None:
    assert [p.name for p in SAMPLE_FILES] == [
        "employee-handbook.md",
        "politica-privacidade.md",
        "regulamento-teletrabalho.pdf",
        "solar-system-notes.txt",
    ]


async def test_reset_removes_existing_documents(container: Container) -> None:
    await seed(container, SAMPLE_FILES[:1])

    await seed(container, SAMPLE_FILES[1:2], reset=True)

    async with container.sessions() as session:
        names = (await session.scalars(select(Document.filename))).all()
    assert names == [SAMPLE_FILES[1].name]
