from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence

from engine.repository.query import RepositoryQuery


@dataclass(frozen=True)
class MaterializationRecord:
    repository_id: str
    commit_sha: str
    path: str
    blob_sha: str
    indexed_status: str  # 'pending', 'indexed', 'failed'
    indexed_at: str


@dataclass(frozen=True)
class MaterializationStats:
    repository_id: str
    commit_sha: str
    total_files: int
    indexed_files: int
    failed_files: int
    pending_files: int


@dataclass(frozen=True)
class MaterializationCoverage:
    known_files: int
    materialized_files: int
    known_bytes: int
    materialized_bytes: int

    @property
    def ratio(self) -> float:
        if self.known_files == 0:
            return 0.0
        return self.materialized_files / self.known_files

    @property
    def percent(self) -> float:
        return self.ratio * 100


class RepositoryStore(RepositoryQuery):
    """
    Abstract repository fact storage interface that extends RepositoryQuery.

    Provides repository/version registration and context-scoping,
    while hiding storage backend details (e.g. SQLite, PostgreSQL, memory).
    """

    @abstractmethod
    def create_repository(self, provider: str, owner: str, name: str) -> str:
        """
        Create a new repository record.

        Returns:
            repository_id: The ID of the created repository.
        """

    @abstractmethod
    def create_version(self, repository_id: str, commit_sha: str) -> str:
        """
        Create a new version record for a repository.

        Returns:
            version_id: The ID of the created version.
        """

    @abstractmethod
    def set_version_context(self, repository_id: str, version_id: str) -> None:
        """
        Scope all queries and writes to this version context.
        """

    @abstractmethod
    def is_materialized(
        self,
        repository_id: str,
        commit_sha: str,
        path: str,
    ) -> bool:
        """Check if a file has been indexed successfully."""

    @abstractmethod
    def get_materialization(
        self,
        repository_id: str,
        commit_sha: str,
        path: str,
    ) -> MaterializationRecord | None:
        """Get the materialization record for a file."""

    @abstractmethod
    def get_materialized_paths(
        self,
        repository_id: str,
        commit_sha: str,
    ) -> Sequence[str]:
        """Get all paths that have been successfully indexed."""

    @abstractmethod
    def get_materialization_stats(
        self,
        repository_id: str,
        commit_sha: str,
    ) -> MaterializationStats:
        """Get indexing statistics for a commit."""

    @abstractmethod
    def get_materialization_coverage(
        self,
        repository_id: str,
        commit_sha: str,
    ) -> MaterializationCoverage:
        """Get coverage details comparing indexed files to repository tree."""

    @abstractmethod
    def record_tree(
        self,
        repository_id: str,
        commit_sha: str,
        entries: Sequence[dict[str, Any]],
    ) -> None:
        """Record the full repository tree for a commit."""

    @abstractmethod
    def record_materialization(
        self,
        repository_id: str,
        commit_sha: str,
        path: str,
        blob_sha: str,
        indexed_status: str,
    ) -> None:
        """Record/update materialization state for a path."""

    @abstractmethod
    def set_indexed_complete(
        self,
        repository_id: str,
        commit_sha: str,
        indexed_complete: bool = True,
    ) -> None:
        """Set whether the commit indexing is fully complete."""

    @abstractmethod
    def get_tree_entries(
        self,
        repository_id: str,
        commit_sha: str,
        paths: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        """Get the tree entries for the specified paths."""

