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



class CommitNotFound(RepositoryError):
    """Raised when a commit is not found."""



class TreeNotFound(RepositoryError):
    """Raised when a tree is not found."""



class TreeTruncated(RepositoryError):
    """Raised when a tree response from provider is truncated/incomplete."""



class FileNotFound(RepositoryError):
    """Raised when a specific file is not found in the repository."""



class BlobUnavailable(RepositoryError):
    """Raised when a blob cannot be fetched/retrieved."""



class AuthenticationFailure(RepositoryError):
    """Raised when authentication with the repository host provider fails."""



class RateLimitExceeded(RepositoryError):
    """Raised when the repository host provider's rate limit is exceeded."""



class RemoteTimeout(RepositoryError):
    """Raised when requests to the repository host provider timeout."""



class PartialBatchFailure(RepositoryError):
    """Raised when a batched file request fails partially.

    Attributes:
        successes: List of successfully retrieved RepositoryBlob objects.
        failures: Dict mapping file paths to the Exception that caused the failure.
    """

    def __init__(self, successes: Any, failures: dict[str, Exception]) -> None:
        message = f"Batch retrieval failed for {len(failures)} files out of {len(failures) + len(successes)}"
        super().__init__(message, details={
            "successes": [b.path for b in successes] if hasattr(successes, "__iter__") else [],
            "failures": {path: str(exc) for path, exc in failures.items()}
        })
        self.successes = successes
        self.failures = failures




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



class LanguageRegistrationError(FactorError):
    """Raised when registering a language plugin fails due to conflicts."""




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
    "CommitNotFound",
    "TreeNotFound",
    "TreeTruncated",
    "FileNotFound",
    "BlobUnavailable",
    "AuthenticationFailure",
    "RateLimitExceeded",
    "RemoteTimeout",
    "PartialBatchFailure",
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
    "LanguageRegistrationError",
    # Cache
    "CacheReadFailed",
    "CacheWriteFailed",
    "CompilationTimeout",
]
