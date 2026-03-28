"""Tests for source_adapters."""

import pytest

from source_adapters.github_adapter import GitHubAdapter
from source_adapters.gitlab_adapter import GitLabAdapter


def test_github_adapter_fetch_not_implemented() -> None:
    a = GitHubAdapter()
    with pytest.raises(NotImplementedError):
        a.fetch_repo_archive("o", "r")


def test_gitlab_adapter_fetch_not_implemented() -> None:
    a = GitLabAdapter()
    with pytest.raises(NotImplementedError):
        a.fetch_project_archive("g/p")
