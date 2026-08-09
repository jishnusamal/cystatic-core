"""Runtime package for Factor pipeline execution.

This package is a compatibility shim. New code should import directly from:
  - core.errors (errors)
  - models (domain models)
  - engine.pipeline (pipeline and context)
"""

from core.errors import (
    CacheReadFailed,
    CacheWriteFailed,
    CompilationTimeout,
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
        from engine.pipeline.context import PipelineContext
        return PipelineContext
    if name == "Pipeline":
        from engine.pipeline.pipeline import Pipeline
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
