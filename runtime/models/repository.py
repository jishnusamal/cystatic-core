"""Repository reference and snapshot models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    def from_full_name(cls, provider: str, full_name: str, default_branch: str = "main") -> RepositoryReference:
        """Create from a full repository name.
        
        Args:
            provider: Integration provider name
            full_name: Full repository name (owner/repo)
            default_branch: Default branch name
            
        Returns:
            RepositoryReference instance
        """
        parts = full_name.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid repository full name: {full_name}")
        return cls(provider=provider, owner=parts[0], repository=parts[1], default_branch=default_branch)


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