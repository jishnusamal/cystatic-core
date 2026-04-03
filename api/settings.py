from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from functools import lru_cache

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    app_name: str = "Cystatic API"
    admin_email: str
    items_per_user: int = 50
    CYSTATIC_KEYS: str
    github_access_token: str
    
    model_config = SettingsConfigDict(env_file=BASE_DIR / "api/.env.local")

@lru_cache
def get_settings():
    return Settings()