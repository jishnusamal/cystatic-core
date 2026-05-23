"""Compatibility re-exports from source_adapters.github package."""

from source_adapters.github.bot import (
    GitHubAdapter,
    GitHubBot,
    GitHubFileSnapshot,
    GitHubFetchResult,
    GitHubPublisher,
    GitHubSource,
    GitHubWebhookBot,
)

__all__ = [
    "GitHubAdapter",
    "GitHubBot",
    "GitHubFileSnapshot",
    "GitHubFetchResult",
    "GitHubPublisher",
    "GitHubSource",
    "GitHubWebhookBot",
]