"""Repository comparison input model for ChangeCompiler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.repository.model import RepositoryModel


@dataclass(frozen=True)
class RepositoryComparison:
    """
    Immutable input model for ChangeCompiler.
    
    Represents a comparison between two repository states.
    This makes invalid combinations impossible.
    
    Attributes:
        base_model: Repository state before changes
        head_model: Repository state after changes
        diff: Git diff between base and head
        base_sha: Base commit SHA
        head_sha: Head commit SHA
    """
    
    base_model: RepositoryModel
    head_model: RepositoryModel
    diff: dict[str, Any]
    base_sha: str
    head_sha: str
    
    def __post_init__(self) -> None:
        """Validate the comparison after initialization."""
        if self.base_model is None:
            raise ValueError("Base model cannot be None")
        
        if self.head_model is None:
            raise ValueError("Head model cannot be None")
        
        if self.diff is None:
            raise ValueError("Diff cannot be None")
        
        if not self.base_sha:
            raise ValueError("Base SHA cannot be empty")
        
        if not self.head_sha:
            raise ValueError("Head SHA cannot be empty")
    
    def is_same_commit(self) -> bool:
        """Check if base and head are the same commit."""
        return self.base_sha == self.head_sha
    
    def get_base_symbols(self) -> frozenset:
        """Get symbols from the base repository model."""
        return self.base_model.symbols
    
    def get_head_symbols(self) -> frozenset:
        """Get symbols from the head repository model."""
        return self.head_model.symbols