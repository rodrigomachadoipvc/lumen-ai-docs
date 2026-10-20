"""Long-lived services, built once at startup and shared by all requests."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from lumen.config import Settings
from lumen.db.session import create_engine, create_session_factory
from lumen.ingestion.pipeline import IngestionService
from lumen.ingestion.worker import IngestionWorker
from lumen.providers.embeddings import EmbeddingProvider, build_embedding_provider
from lumen.storage import FileStorage


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    storage: FileStorage
    embedder: EmbeddingProvider
    ingestion: IngestionService
    worker: IngestionWorker

    @classmethod
    def build(cls, settings: Settings, *, embedder: EmbeddingProvider | None = None) -> Container:
        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        storage = FileStorage(settings.upload_dir)
        embedder = embedder or build_embedding_provider(settings)
        ingestion = IngestionService(
            session_factory=sessions, storage=storage, embedder=embedder, settings=settings
        )
        return cls(
            settings=settings,
            engine=engine,
            sessions=sessions,
            storage=storage,
            embedder=embedder,
            ingestion=ingestion,
            worker=IngestionWorker(ingestion.process),
        )

    async def start(self) -> None:
        self.worker.start()
        for document_id in await self.ingestion.pending_documents():
            self.worker.enqueue(document_id)

    async def close(self) -> None:
        await self.worker.stop()
        await self.engine.dispose()
