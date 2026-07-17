# api/settings.py

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.

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

    AI_API_KEY: str
    AI_API_BASE_URL: str = "https://api.groq.com/openai/v1"
    AI_MODEL: str = "openai/gpt-oss-120b"

    CYSTATIC_KEYS: dict[str, str] = Field(default_factory=dict)

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Cached application settings.

    Safe to import anywhere.

        from api.settings import get_settings

        settings = get_settings()
    """
    return Settings()  # type: ignore[call-arg]