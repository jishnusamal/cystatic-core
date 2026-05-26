from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from functools import lru_cache

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    app_name: str = "Factor API"
    admin_email: str = ""
    items_per_user: int = 50
    cystatic_keys: str = ""
    github_access_token: str = ""
    github_app_id: str = ""
    github_app_client_id: str = ""
    github_client_secret: str = ""
    github_private_key: str = ""
    github_webhook_secret: str = ""
    sentry_dsn: str = ""
    app_env: str = ""
    app_version: str = ""
    database_url: str = ""
    database_url_direct: str = ""
    ai_api_key: str = ""
    llm_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"
    llm_base_url: str = "https://api.groq.com/openai/v1"

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env.local")

@lru_cache
def get_settings():
    return Settings()