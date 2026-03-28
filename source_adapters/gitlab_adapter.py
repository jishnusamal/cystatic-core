"""GitLab source adapter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GitLabFetchResult:
    """Placeholder for fetched GitLab archive or tree contents."""

    content: bytes
    ref: str
    project: str


class GitLabAdapter:
    """Fetches code from GitLab (implementation stub)."""

    def __init__(self, token: str | None = None, base_url: str | None = None) -> None:
        self._token = token
        self._base_url = base_url or "https://gitlab.com"

    def fetch_project_archive(self, project: str, ref: str = "main") -> GitLabFetchResult:
        """Return a snapshot of the project at ``ref``."""
        raise NotImplementedError("GitLab archive fetch not implemented yet")
