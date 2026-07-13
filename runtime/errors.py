"""Typed runtime errors for the pipeline.

No generic exceptions outside the pipeline.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Base exception for all pipeline errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


# Repository errors

class RepositoryNotSupported(PipelineError):
    """Raised when a repository language is not supported."""
    pass


class RepositoryCompilationFailed(PipelineError):
    """Raised when repository model compilation fails."""
    pass


class RepositoryNotInstalled(PipelineError):
    """Raised when required language tooling is not installed."""
    pass


# Diff errors

class DiffFetchFailed(PipelineError):
    """Raised when fetching a diff fails."""
    pass


class InvalidDiff(PipelineError):
    """Raised when diff data is malformed."""
    pass


# Webhook errors

class InvalidWebhook(PipelineError):
    """Raised when webhook verification fails."""
    pass


class MissingWebhookPayload(PipelineError):
    """Raised when required webhook payload fields are missing."""
    pass


# Language errors

class LanguageNotSupported(PipelineError):
    """Raised when a language adapter is not available."""
    pass


class LanguageDetectionFailed(PipelineError):
    """Raised when language detection fails."""
    pass


# Rendering errors

class RendererFailed(PipelineError):
    """Raised when rendering fails."""
    pass


class JSONSerializationFailed(PipelineError):
    """Raised when JSON serialization fails."""
    pass


# Cache errors

class CacheReadFailed(PipelineError):
    """Raised when reading from cache fails."""
    pass


class CacheWriteFailed(PipelineError):
    """Raised when writing to cache fails."""
    pass


# Pipeline execution errors

class PipelineExecutionError(PipelineError):
    """Raised when pipeline execution fails."""
    pass


class CompilationTimeout(PipelineError):
    """Raised when compilation exceeds timeout."""
    pass