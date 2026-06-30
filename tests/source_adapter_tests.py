"""Tests for source_adapters."""

import pytest

from source_adapters.github.bot import GitHubAdapter


def test_github_adapter_requires_token() -> None:
    """GitHubAdapter requires a valid token."""
    a = GitHubAdapter()
    with pytest.raises(ValueError, match="GitHub token is required"):
        a.fetch_repo_archive("o", "r")

