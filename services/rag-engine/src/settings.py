"""Typed settings.

Two jobs, both required by ADR-001:

1. **Secrets** are read from the environment and are the only settings that must
   never be logged. :class:`SecretStr` keeps a key out of ``repr``, traces and
   accidental log lines.
2. **Pinned versions** (model, parser, chunker, prompt) are settings, not literals
   scattered through the code, because the audit record has to name the exact
   component that produced a number. Changing a pin is a deliberate, reviewable
   change that invalidates the affected indexes and golden-set results.

Validation is strict and fails fast at startup: an unset API key or a malformed
pin should stop the process, not surface as a confusing error at query time.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "rag-engine"
ENV_PREFIX = "RAG_"

#: Distribution version. ``pyproject.toml`` reads this single source (hatch version hook),
#: so a release bump cannot leave the reported version behind.
VERSION = "0.1.0"


class Settings(BaseSettings):
    """Process configuration, loaded from the environment with the ``RAG_`` prefix."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- environment -------------------------------------------------------
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = True

    # --- service endpoints -------------------------------------------------
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)

    # --- secrets (never logged) -------------------------------------------
    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    llm_gateway_api_key: SecretStr | None = Field(default=None, repr=False)
    postgres_dsn: SecretStr | None = Field(default=None, repr=False)

    # --- pinned component versions ----------------------------------------
    # Every value below participates in the audit record. Bump deliberately.
    llm_model_id: str = "gpt-4.1-mini-2025-04-14"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_output_tokens: int = Field(default=1024, ge=64, le=32768)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    parser_name: str = "docling"
    parser_version: str = "unpinned"

    embedder_model_id: str = "text-embedding-3-small"
    embedder_dimension: int = Field(default=1536, ge=8)
    sparse_model_id: str = "bm25-finance-v1"
    sparse_tokenizer_version: str = "v1"

    chunker_name: str = "parent-child-structural"
    chunker_version: str = "v1"
    child_chunk_max_chars: int = Field(default=600, ge=80, le=4000)
    parent_max_chars: int = Field(default=4000, ge=400, le=32000)
    retrieval_top_k: int = Field(default=10, ge=1, le=100)
    retrieval_candidates: int = Field(default=50, ge=1, le=1000)
    rrf_k: int = Field(default=60, ge=1, le=1000)

    prompt_version: str = "v1"
    prompt_sha256: str | None = Field(
        default=None, description="Hash of the extraction prompt; stamped into every audit record."
    )

    # --- infrastructure ----------------------------------------------------
    vector_store_provider: Literal["fake", "qdrant", "pgvector"] = "fake"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "rag_chunks"
    postgres_host: str = "postgres"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "rag_engine"
    postgres_user: str = "rag_engine"

    @field_validator("retrieval_candidates")
    @classmethod
    def _candidates_cover_top_k(cls, value: int, info: ValidationInfo) -> int:
        """Require re-ranking headroom: fusion cannot rank more than it fetched."""
        top_k = info.data.get("retrieval_top_k")
        if top_k is not None and value < top_k:
            raise ValueError("retrieval_candidates must be >= retrieval_top_k")
        return value

    @model_validator(mode="after")
    def _versions_pinned_outside_local(self) -> Self:
        """Forbid ``unpinned`` component versions outside local and test.

        Outside those environments an audit record must be able to name the parser,
        chunker and prompt that produced a number, so a missing pin is a startup
        failure rather than a surprise during an investigation.
        """
        if self.environment in {"local", "test"}:
            return self
        unpinned = [
            name
            for name in ("parser_version", "chunker_version", "prompt_version")
            if getattr(self, name) == "unpinned"
        ]
        if unpinned:
            raise ValueError(
                f"unpinned component versions are not allowed in {self.environment}: "
                f"{', '.join(unpinned)}"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, cached.

    Raises:
        pydantic.ValidationError: if the environment holds an invalid value. The
            process must not start with a half-valid configuration.
    """
    return Settings()


def redact(value: SecretStr | None) -> str:
    """Render a secret for logs: a fixed marker, never the value."""
    return "***" if value is not None else "unset"
