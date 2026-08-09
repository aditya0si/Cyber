"""Typed application settings (docs/17 Â§6, docs/21 Task 0.1).

Phase 1 exposes a minimal Settings surface; Phase 4 onwards adds auth/billing/
LLM knobs. Loaded from environment via pydantic-settings in strict mode.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    LOCAL = "local"
    CI = "ci"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    """Environment-driven application settings; secrets come via env at boot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    env: Env = Env.LOCAL
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://cybersim:cybersim_dev@localhost:5432/cybersim"
    redis_url: str = "redis://localhost:6379/0"

    llm_provider: Literal["openai", "anthropic", "ollama", "fake"] = "openai"
    llm_model_triage: str = "gpt-4o-mini"
    llm_model_analysis: str = "gpt-4o"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    knowledge_embed_model: str = "text-embedding-3-small"

    jwt_kid: str = "dev-1"
    jwt_issuer: str = "http://localhost:8000"
    jwt_access_ttl_sec: int = Field(default=900, ge=60)
    jwt_refresh_ttl_sec: int = Field(default=2_592_000, ge=3600)

    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "https://m.cybersim.local"]
    )

    stripe_mode: Literal["test", "live"] = "test"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = "sim_price_pro"

    graph_backend: Literal["nx", "neo4j"] = "nx"

    object_store_endpoint: str = "http://localhost:9000"
    object_store_access_key: str = ""
    object_store_secret_key: str = ""
    object_store_bucket: str = "cybersim"

    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    @property
    def ai_enabled(self) -> bool:
        """True when a real LLM provider key is present (and not the fake adapter)."""
        if self.llm_provider == "fake":
            return False
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        return self.llm_provider == "ollama"


def get_settings() -> Settings:
    """Return a fresh Settings instance from environment (no caching layer upstream)."""
    return Settings()
