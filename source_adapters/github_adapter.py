"""GitHub source adapter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GitHubFetchResult:
    """Placeholder for fetched GitHub archive or tree contents."""

    content: bytes
    ref: str
    repo: str


class GitHubAdapter:
    """Fetches code from GitHub (implementation stub)."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token

    def fetch_repo_archive(self, owner: str, repo: str, ref: str = "main") -> GitHubFetchResult:
        """Return a snapshot of the repository at ``ref``."""
        raise NotImplementedError("GitHub archive fetch not implemented yet")
