"""Application and compiler configuration.

Merges API settings (api/settings.py) and runtime compiler bounds
(runtime/settings.py) into a single, canonical config module.

Usage:
    from core.config import get_settings, get_compiler_settings
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration.

    Values are loaded from:
      1. Environment variables
      2. .env file (development)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"

    ADMIN_EMAIL: str

    # ------------------------------------------------------------------
    # API Keys
    # ------------------------------------------------------------------

    AI_API_KEY: str | None = None
    # AI_API_BASE_URL: str = "https://api.groq.com/openai/v1"
    # AI_MODEL: str = "openai/gpt-oss-120b"
    AI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    AI_MODEL: str = "gemini-3.6-flash"

    # CYSTATIC_KEYS: dict[str, str] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    DATABASE_URL: str
    DATABASE_URL_DIRECT: str

    # ------------------------------------------------------------------
    # GitHub
    # ------------------------------------------------------------------

    GITHUB_ACCESS_TOKEN: str | None = None

    GITHUB_APP_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str

    GITHUB_PRIVATE_KEY: str

    GITHUB_APP_WEBHOOK_SECRET: str

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------

    UPSTASH_REDIS_REST_URL: str
    UPSTASH_REDIS_REST_TOKEN: str

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    SENTRY_DSN: str | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


class CompilerSettings(BaseSettings):
    """Compiler configuration settings.

    Controls bounds and limits on the LLMContextCompiler stages to prevent
    graph explosion.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    LLM_CONTEXT_MAX_REVIEW_SCOPE_DEPTH: int = 3
    LLM_CONTEXT_MAX_CHILDREN_PER_NODE: int = 8
    LLM_CONTEXT_MAX_EXECUTION_CHAIN_LENGTH: int = 20
    LLM_CONTEXT_MAX_DISCOVERY_REFERENCES: int = 8
    LLM_CONTEXT_MAX_ENDPOINTS: int = 50
    LLM_CONTEXT_MAX_SYMBOLS_PER_FILE: int = 50
    LLM_CONTEXT_MAX_REFERENCES_PER_NODE: int = 8
    LLM_CONTEXT_MAX_DISCOVERY_EVIDENCE: int = 8


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached application settings.

    Safe to import anywhere.

        from core.config import get_settings

        settings = get_settings()
    """
    return Settings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_compiler_settings() -> CompilerSettings:
    """Cached compiler settings."""
    return CompilerSettings()
