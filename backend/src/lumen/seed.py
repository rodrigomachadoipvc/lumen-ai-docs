"""Load the demo documents from data/samples into the database.

    uv run python -m lumen.seed            # add the samples (already-loaded files are skipped)
    uv run python -m lumen.seed --reset    # delete every document first

Run `uv run alembic upgrade head` once before seeding.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import delete

from lumen.config import Settings, get_settings
from lumen.container import Container
from lumen.db.models import Document, DocumentStatus
from lumen.ingestion.uploads import DuplicateDocumentError, register_upload
from lumen.logging_config import configure_logging

DEFAULT_SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples"
SUPPORTED_SUFFIXES = {".pdf", ".md", ".markdown", ".txt"}


def sample_files(samples_dir: Path) -> list[Path]:
    """Loadable files directly inside `samples_dir`, excluding its README."""
    return sorted(
        p
        for p in samples_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and p.stem.upper() != "README"
    )


async def seed(container: Container, files: list[Path], *, reset: bool = False) -> int:
    """Load `files` and process them one by one. Returns the number of failures."""
    failures = 0
    if reset:
        async with container.sessions() as session:
            ids = list(await session.scalars(delete(Document).returning(Document.id)))
            await session.commit()
        for document_id in ids:
            await asyncio.to_thread(container.storage.delete, document_id)
        print(f"Deleted {len(ids)} document(s).")

    for path in files:
        data = await asyncio.to_thread(path.read_bytes)
        async with container.sessions() as session:
            try:
                document = await register_upload(session, container.storage, path.name, data)
            except DuplicateDocumentError:
                print(f"  skip   {path.name} (already loaded)")
                continue
        print(f"  load   {path.name} ...", flush=True)
        await container.ingestion.process(document.id)
        async with container.sessions() as session:
            result = await session.get(Document, document.id)
        if result is not None and result.status is DocumentStatus.READY:
            print(f"  ready  {path.name} ({result.chunk_count} chunks, {result.language})")
        else:
            failures += 1
            error = result.error if result else "deleted"
            print(f"  FAIL   {path.name}: {error}")
    return failures


async def _run(settings: Settings, files: list[Path], *, reset: bool) -> int:
    container = Container.build(settings)
    try:
        return await seed(container, files, reset=reset)
    finally:
        await container.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--reset", action="store_true", help="delete all documents first")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging("WARNING", json=False)  # keep the console readable
    print(f"Seeding from {args.samples_dir} using {settings.embedding_model}")
    failures = asyncio.run(_run(settings, sample_files(args.samples_dir), reset=args.reset))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
