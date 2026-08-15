from abc import abstractmethod

from engine.repository.query import RepositoryQuery


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
