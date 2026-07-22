"""Runtime package for Cystatic pipeline execution."""

from runtime.errors import (
    CompilationTimeout,
    CacheReadFailed,
    CacheWriteFailed,
    DiffFetchFailed,
    InvalidDiff,
    InvalidWebhook,
    JSONSerializationFailed,
    LanguageDetectionFailed,
    LanguageNotSupported,
    MissingWebhookPayload,
    PipelineError,
    PipelineExecutionError,
    RendererFailed,
    RepositoryCompilationFailed,
    RepositoryNotInstalled,
    RepositoryNotSupported,
)
from typing import Any

def __getattr__(name: str) -> Any:
    if name == "PipelineContext":
        from runtime.pipeline.context import PipelineContext
        return PipelineContext
    if name == "Pipeline":
        from runtime.pipeline.pipeline import Pipeline
        return Pipeline
    raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = [
    # Errors
    "PipelineError",
    "RepositoryNotSupported",
    "RepositoryCompilationFailed",
    "RepositoryNotInstalled",
    "DiffFetchFailed",
    "InvalidDiff",
    "InvalidWebhook",
    "MissingWebhookPayload",
    "LanguageNotSupported",
    "LanguageDetectionFailed",
    "RendererFailed",
    "JSONSerializationFailed",
    "CacheReadFailed",
    "CacheWriteFailed",
    "PipelineExecutionError",
    "CompilationTimeout",
    # Core
    "Pipeline",
    "PipelineContext",
]