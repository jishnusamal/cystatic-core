"""Core errors for the Factor platform.

Absorbs all content from the root-level errors/ package into a single file.
All error imports throughout the codebase should reference core.errors.
"""

from __future__ import annotations

# ─── Base errors ────────────────────────────────────────────────────────────


class FactorError(Exception):
    """Base exception for all Factor errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ─── Authentication errors ───────────────────────────────────────────────────


class AuthenticationError(FactorError):
    """Raised when authentication fails."""



# ─── Repository errors ───────────────────────────────────────────────────────


class RepositoryError(FactorError):
    """Base exception for repository errors."""



class RepositoryNotFound(RepositoryError):
    """Raised when a repository cannot be found."""



class RepositoryAccessDenied(RepositoryError):
    """Raised when access to a repository is denied."""



# ─── Webhook errors ──────────────────────────────────────────────────────────


class WebhookError(FactorError):
    """Base exception for webhook errors."""



class WebhookVerificationError(WebhookError):
    """Raised when webhook signature verification fails."""



# ─── Renderer errors ─────────────────────────────────────────────────────────


class RendererError(FactorError):
    """Base exception for renderer errors."""



class RenderingError(RendererError):
    """Raised when rendering fails."""



# ─── Pipeline errors ─────────────────────────────────────────────────────────


class PipelineError(FactorError):
    """Base exception for all pipeline errors."""



class PipelineExecutionError(PipelineError):
    """Raised when pipeline execution fails."""



# ─── Pipeline sub-errors (from runtime/errors.py) ────────────────────────────


class RepositoryNotSupported(PipelineError):
    """Raised when a repository language is not supported."""



class RepositoryCompilationFailed(PipelineError):
    """Raised when repository model compilation fails."""



class RepositoryNotInstalled(PipelineError):
    """Raised when required language tooling is not installed."""



class DiffFetchFailed(PipelineError):
    """Raised when fetching a diff fails."""



class InvalidDiff(PipelineError):
    """Raised when diff data is malformed."""



class InvalidWebhook(PipelineError):
    """Raised when webhook verification fails."""



class MissingWebhookPayload(PipelineError):
    """Raised when required webhook payload fields are missing."""



class LanguageNotSupported(PipelineError):
    """Raised when a language adapter is not available."""



class LanguageDetectionFailed(PipelineError):
    """Raised when language detection fails."""



class RendererFailed(PipelineError):
    """Raised when rendering fails."""



class JSONSerializationFailed(PipelineError):
    """Raised when JSON serialization fails."""



class CacheReadFailed(PipelineError):
    """Raised when reading from cache fails."""



class CacheWriteFailed(PipelineError):
    """Raised when writing to cache fails."""



class CompilationTimeout(PipelineError):
    """Raised when compilation exceeds timeout."""



__all__ = [
    # Base
    "FactorError",
    # Auth
    "AuthenticationError",
    # Repository
    "RepositoryError",
    "RepositoryNotFound",
    "RepositoryAccessDenied",
    "RepositoryNotSupported",
    "RepositoryCompilationFailed",
    "RepositoryNotInstalled",
    # Webhook
    "WebhookError",
    "WebhookVerificationError",
    "InvalidWebhook",
    "MissingWebhookPayload",
    # Renderer
    "RendererError",
    "RenderingError",
    "RendererFailed",
    "JSONSerializationFailed",
    # Pipeline
    "PipelineError",
    "PipelineExecutionError",
    # Diff
    "DiffFetchFailed",
    "InvalidDiff",
    # Language
    "LanguageNotSupported",
    "LanguageDetectionFailed",
    # Cache
    "CacheReadFailed",
    "CacheWriteFailed",
    "CompilationTimeout",
]
