# runtime/settings.py

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class CompilerSettings(BaseSettings):
    """
    Compiler configuration settings.
    
    Controls bounds and limits on the LLMContextCompiler stages to prevent graph explosion.
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
def get_compiler_settings() -> CompilerSettings:
    """
    Cached compiler settings.
    """
    return CompilerSettings()
