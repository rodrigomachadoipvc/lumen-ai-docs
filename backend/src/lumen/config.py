"""Application settings, loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field can be set with a `LUMEN_` environment variable."""

    model_config = SettingsConfigDict(
        env_prefix="LUMEN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Lumen API"
    environment: Literal["local", "test", "production"] = "local"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
