"""GitHub API client factory helpers."""

from __future__ import annotations

from source_adapters.github.bot import GitHubPublisher, GitHubSource


def build_github_clients(token: str, base_url: str | None = None) -> tuple[GitHubSource, GitHubPublisher]:
    source = GitHubSource(token=token, base_url=base_url)
    publisher = GitHubPublisher(token=token, base_url=base_url)
    return source, publisher

def build_public_github_client(
    token: str, 
    base_url: str | None = None,
) -> GitHubSource:
    return GitHubSource(token=token, base_url=base_url)
