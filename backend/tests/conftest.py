"""Shared fixtures. Integration tests run against a real PostgreSQL + pgvector in Docker."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from lumen.config import Settings
from lumen.container import Container
from lumen.main import create_app
from tests.fakes import FakeChat, FakeEmbeddings

BACKEND_DIR = Path(__file__).resolve().parent.parent
POSTGRES_IMAGE = "pgvector/pgvector:0.8.7-pg18"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        config.set_main_option("sqlalchemy.url", url)
        config.attributes["configure_logger"] = False
        command.upgrade(config, "head")
        yield url


@pytest.fixture
def settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # ignore the developer's .env
        environment="test",
        log_json=False,
        log_level="WARNING",
        database_url=database_url,
        upload_dir=tmp_path / "uploads",
    )


@pytest.fixture
def embedder() -> FakeEmbeddings:
    return FakeEmbeddings()


@pytest.fixture
def chat() -> FakeChat:
    return FakeChat()


@pytest.fixture
async def app(
    settings: Settings, embedder: FakeEmbeddings, chat: FakeChat
) -> AsyncIterator[FastAPI]:
    application = create_app(settings, embedder=embedder, chat=chat)
    async with application.router.lifespan_context(application):
        yield application
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE documents, chats CASCADE"))
    await engine.dispose()


@pytest.fixture
def container(app: FastAPI) -> Container:
    result: Container = app.state.container
    return result


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
