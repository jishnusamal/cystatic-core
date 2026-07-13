"""Pull request reference model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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