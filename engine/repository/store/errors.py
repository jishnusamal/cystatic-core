class RepositoryStoreError(Exception):
    """Base exception for all repository store operations."""
    pass


class RepositoryNotFoundError(RepositoryStoreError):
    """Raised when a requested repository does not exist in the store."""
    pass


class VersionNotFoundError(RepositoryStoreError):
    """Raised when a requested repository version does not exist in the store."""
    pass
