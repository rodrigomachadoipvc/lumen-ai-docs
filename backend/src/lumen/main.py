"""ASGI entry point."""

import structlog
from fastapi import FastAPI

from lumen.api import health
from lumen.config import Settings, get_settings
from lumen.logging_config import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application. Tests pass their own settings."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    app = FastAPI(title=settings.app_name)
    app.include_router(health.router)

    structlog.get_logger(__name__).info("app_created", environment=settings.environment)
    return app


app = create_app()
