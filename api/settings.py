from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from functools import lru_cache

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    app_name: str = "Cystatic API"
    admin_email: str = ""
    items_per_user: int = 50
    cystatic_keys: str = ""
    github_access_token: str = ""
    sentry_dsn: str = ""
    app_env: str = ""
    app_version: str = ""
    database_url: str = ""
    database_url_direct: str = ""
    ai_api_key: str = ""
    llm_api_key: str = ""
    llm_model: str = "qwen-3-235b-a22b-instruct-2507"
    llm_base_url: str = "https://api.cerebras.ai/v1"
    
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env.local")

@lru_cache
def get_settings():
    return Settings()