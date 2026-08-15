class RepositoryStoreError(Exception):
    """Base exception for all repository store operations."""



class RepositoryNotFoundError(RepositoryStoreError):
    """Raised when a requested repository does not exist in the store."""



class VersionNotFoundError(RepositoryStoreError):
    """Raised when a requested repository version does not exist in the store."""

