"""Repository provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from runtime.models import RepositoryReference, RepositorySnapshot, DiffSnapshot


class RepositoryProvider(ABC):
    """Responsible for reading repository state.
    
    It never posts comments.
    It never verifies webhooks.
    """
    
    @abstractmethod
    async def fetch_repository(self, repo_ref: RepositoryReference) -> RepositorySnapshot:
        """Fetch the complete repository state.
        
        Args:
            repo_ref: Repository reference
            
        Returns:
            Repository snapshot with tree, files, and commit info
        """
        pass
    
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
        pass
    
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
        pass
    
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
        pass
    
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
        pass
    
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
        pass