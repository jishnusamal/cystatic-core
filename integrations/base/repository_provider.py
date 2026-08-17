"""Repository provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Sequence

from models.core import DiffSnapshot, RepositoryReference, RepositorySnapshot


class RepositoryAcquisitionMode(str, Enum):
    ZIP = "zip"
    GIT = "git"


@dataclass(frozen=True)
class RepositoryCommit:
    sha: str
    repository: str
    message: str | None = None
    author: str | None = None


@dataclass(frozen=True)
class RepositoryTreeEntry:
    path: str
    type: Literal["blob", "tree"]
    sha: str
    size: int | None = None


@dataclass(frozen=True)
class RepositoryBlob:
    path: str
    sha: str
    size: int
    content: bytes


class RepositoryProvider(ABC):
    """Responsible for reading repository state.

    It never posts comments.
    It never verifies webhooks.
    """

    @abstractmethod
    async def fetch_repository(
        self, repo_ref: RepositoryReference
    ) -> RepositorySnapshot:
        """Fetch the complete repository state.

        Args:
            repo_ref: Repository reference

        Returns:
            Repository snapshot with tree, files, and commit info
        """

    @abstractmethod
    async def fetch_repository_at_sha(
        self, repo_ref: RepositoryReference, sha: str
    ) -> RepositorySnapshot:
        """Fetch the repository state at a specific commit.

        Args:
            repo_ref: Repository reference
            sha: Commit SHA to fetch

        Returns:
            Repository snapshot at the specified commit
        """

    @abstractmethod
    async def fetch_diff(
        self,
        repo_ref: RepositoryReference,
        base_sha: str,
        head_sha: str,
    ) -> DiffSnapshot:
        """Fetch the diff between two commits.

        Args:
            repo_ref: Repository reference
            base_sha: Base commit SHA
            head_sha: Head commit SHA

        Returns:
            Diff snapshot with changed files and hunks
        """

    @abstractmethod
    async def fetch_file(
        self,
        repo_ref: RepositoryReference,
        file_path: str,
        sha: str,
    ) -> str:
        """Fetch a single file at a specific commit.

        Args:
            repo_ref: Repository reference
            file_path: Path to the file
            sha: Commit SHA

        Returns:
            File content as string
        """

    @abstractmethod
    async def fetch_tree(
        self,
        repo_ref: RepositoryReference,
        sha: str,
    ) -> dict[str, Any]:
        """Fetch the file tree at a specific commit.

        Args:
            repo_ref: Repository reference
            sha: Commit SHA

        Returns:
            Tree structure
        """

    @abstractmethod
    async def fetch_commit(
        self,
        repo_ref: RepositoryReference,
        sha: str,
    ) -> dict[str, Any]:
        """Fetch commit information.

        Args:
            repo_ref: Repository reference
            sha: Commit SHA

        Returns:
            Commit information
        """

    @abstractmethod
    async def get_commit(
        self,
        repository: str,
        sha: str,
    ) -> RepositoryCommit:
        """Fetch commit metadata.

        Args:
            repository: Full repository name (owner/repo)
            sha: Commit SHA to fetch

        Returns:
            RepositoryCommit object
        """

    @abstractmethod
    async def get_tree(
        self,
        repository: str,
        sha: str,
    ) -> Sequence[RepositoryTreeEntry]:
        """Fetch repository tree metadata.

        Args:
            repository: Full repository name (owner/repo)
            sha: Commit SHA

        Returns:
            Sequence of RepositoryTreeEntry objects
        """

    @abstractmethod
    async def get_file(
        self,
        repository: str,
        path: str,
        ref: str,
    ) -> RepositoryBlob:
        """Fetch a single file blob.

        Args:
            repository: Full repository name (owner/repo)
            path: File path
            ref: Commit SHA or ref

        Returns:
            RepositoryBlob object
        """

    @abstractmethod
    async def get_files(
        self,
        repository: str,
        paths: Sequence[str],
        ref: str,
    ) -> Sequence[RepositoryBlob]:
        """Fetch multiple file blobs.

        Args:
            repository: Full repository name (owner/repo)
            paths: File paths to fetch
            ref: Commit SHA or ref

        Returns:
            Sequence of RepositoryBlob objects
        """
