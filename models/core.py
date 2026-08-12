"""Core domain models: repository, pull request, and diff references.

Absorbed from runtime/models/repository.py, pull_request.py, and diff.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─── Repository ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RepositoryReference:
    """Platform-agnostic reference to a repository.

    Attributes:
        provider: Integration provider name (e.g., "github", "gitlab")
        owner: Repository owner/organization
        repository: Repository name
        default_branch: Default branch name (e.g., "main", "master")
    """

    provider: str
    owner: str
    repository: str
    default_branch: str = "main"

    @property
    def full_name(self) -> str:
        """Get the full repository name (owner/repo)."""
        return f"{self.owner}/{self.repository}"

    @classmethod
    def from_full_name(
        cls, provider: str, full_name: str, default_branch: str = "main"
    ) -> "RepositoryReference":
        """Create from a full repository name."""
        parts = full_name.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid repository full name: {full_name}")
        return cls(
            provider=provider,
            owner=parts[0],
            repository=parts[1],
            default_branch=default_branch,
        )


@dataclass(frozen=True)
class RepositorySnapshot:
    """Represents a downloaded repository snapshot.

    Attributes:
        tree: File tree structure
        files: Dictionary of file_path -> content
        commit: Commit information
    """

    tree: dict[str, Any]
    files: dict[str, str]
    commit: str


# ─── Pull Request ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PullRequestReference:
    """Platform-agnostic reference to a pull request.

    Attributes:
        number: Pull request number
        base_sha: Base commit SHA
        head_sha: Head commit SHA
        title: Pull request title
    """

    number: int
    base_sha: str
    head_sha: str
    title: str

    @property
    def base_ref(self) -> str:
        """Get the base reference (e.g., 'refs/heads/main')."""
        return f"refs/heads/{self.base_sha}"

    @property
    def head_ref(self) -> str:
        """Get the head reference (e.g., 'refs/heads/feature-branch')."""
        return f"refs/heads/{self.head_sha}"


# ─── Diff ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DiffHunk:
    """Represents a single hunk in a diff."""

    file_path: str
    source_start: int
    source_length: int
    target_start: int
    target_length: int
    added_lines: tuple[int, ...] = field(default_factory=tuple)
    removed_lines: tuple[int, ...] = field(default_factory=tuple)
    lines: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiffFile:
    """Represents a file in a diff."""

    file_path: str
    added_lines: tuple[int, ...] = field(default_factory=tuple)
    removed_lines: tuple[int, ...] = field(default_factory=tuple)
    hunks: tuple[DiffHunk, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiffSnapshot:
    """Represents a complete diff snapshot."""

    files: tuple[DiffFile, ...] = field(default_factory=tuple)
    patches: tuple[str, ...] = field(default_factory=tuple)
    base_sha: str = ""
    head_sha: str = ""
