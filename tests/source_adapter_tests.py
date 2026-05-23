"""Tests for source_adapters."""

import pytest

from source_adapters.github_adapter import GitHubAdapter
from source_adapters.gitlab_adapter import GitLabAdapter


def test_github_adapter_requires_token() -> None:
    """GitHubAdapter requires a valid token."""
    a = GitHubAdapter()
    with pytest.raises(ValueError, match="GitHub token is required"):
        a.fetch_repo_archive("o", "r")


def test_gitlab_adapter_fetch_not_implemented() -> None:
    a = GitLabAdapter()
    with pytest.raises(NotImplementedError):
        a.fetch_project_archive("g/p")
