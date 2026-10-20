"""ASGI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lumen.api import documents, health, search
from lumen.api.errors import register_error_handlers
from lumen.config import Settings, get_settings
from lumen.container import Container
from lumen.logging_config import configure_logging
from lumen.providers.embeddings import EmbeddingProvider


def create_app(
    settings: Settings | None = None, *, embedder: EmbeddingProvider | None = None
) -> FastAPI:
    """Build the FastAPI application. Tests pass their own settings and fake providers."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = Container.build(settings, embedder=embedder)
        app.state.container = container
        await container.start()
        try:
            yield
        finally:
            await container.close()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(search.router)

    structlog.get_logger(__name__).info("app_created", environment=settings.environment)
    return app


app = create_app()
