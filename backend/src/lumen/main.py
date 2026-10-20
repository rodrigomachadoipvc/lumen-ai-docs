"""ASGI entry point."""

from fastapi import FastAPI

from lumen.api import health
from lumen.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application. Tests pass their own settings."""
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name)
    app.include_router(health.router)
    return app


app = create_app()
