"""Application settings, loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# The `chunks.embedding` column is created with this many dimensions (see the first migration).
EMBEDDING_DIMENSIONS = 1024


class Settings(BaseSettings):
    """Runtime configuration. Every field can be set with a `LUMEN_` environment variable."""

    model_config = SettingsConfigDict(
        env_prefix="LUMEN_",
        # Repository-root `.env` (shared with docker compose), then an optional backend override.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Lumen API"
    environment: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    # Browser origins allowed to call the API (the Next.js dev server by default).
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- Database -------------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://lumen:lumen@localhost:5432/lumen"

    # --- Uploads --------------------------------------------------------------------
    upload_dir: Path = Path("../data/uploads")
    max_upload_mb: int = Field(default=25, ge=1, le=200)

    # --- Chunking (sizes in approximate tokens; 1 token ~ 4 characters) ------------------
    chunk_size_tokens: int = Field(default=350, ge=50, le=2000)
    chunk_overlap_tokens: int = Field(default=50, ge=0, le=500)

    # --- Embeddings -----------------------------------------------------------------
    embedding_provider: Literal["ollama", "openai"] = "ollama"
    embedding_model: str = "qwen3-embedding:0.6b"
    # Qwen3-Embedding expects an instruction before queries (not before documents).
    embedding_query_instruction: str = (
        "Instruct: Given a question, retrieve passages from documents that answer it\nQuery: "
    )
    embedding_batch_size: int = Field(default=16, ge=1, le=256)

    # --- Providers ------------------------------------------------------------------
    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
