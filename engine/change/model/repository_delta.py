"""Repository delta model - represents a transition between two repository states.

This is the fundamental input for all compiler phases after repository compilation.
Factor compiles repository transitions, not individual snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.repository.model import RepositoryModel


@dataclass(frozen=True)
class RepositoryDelta:
    """
    Immutable model representing a repository transition.

    This is the canonical input for all compiler phases after repository compilation.
    Every deterministic fact is derived from comparing the before and after states.

    Attributes:
        base_model: Repository state before changes
        head_model: Repository state after changes
        diff: Git diff between base and head
        base_sha: Base commit SHA
        head_sha: Head commit SHA
    """

    base_model: RepositoryModel | None
    head_model: RepositoryModel | None
    diff: dict[str, Any]
    base_sha: str
    head_sha: str

    def __post_init__(self) -> None:
        """Validate the delta after initialization."""
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

        # Pre-compute and store symbol IDs before models are released
        object.__setattr__(
            self, "_base_symbol_ids", frozenset(s.id for s in self.base_model.symbols)
        )
        object.__setattr__(
            self, "_head_symbol_ids", frozenset(s.id for s in self.head_model.symbols)
        )

    def release_base_model(self) -> None:
        """Release the base repository model reference to free memory."""
        object.__setattr__(self, "base_model", None)

    def release_head_model(self) -> None:
        """Release the head repository model reference to free memory."""
        object.__setattr__(self, "head_model", None)

    def is_same_commit(self) -> bool:
        """Check if base and head are the same commit."""
        return self.base_sha == self.head_sha

    def get_base_symbols(self) -> frozenset:
        """Get symbols from the base repository model."""
        if self.base_model is None:
            raise ValueError("Base repository model has been released")
        return self.base_model.symbols

    def get_head_symbols(self) -> frozenset:
        """Get symbols from the head repository model."""
        if self.head_model is None:
            raise ValueError("Head repository model has been released")
        return self.head_model.symbols

    def get_base_symbol_ids(self) -> frozenset[str]:
        """Get symbol IDs from the base repository model."""
        return self._base_symbol_ids

    def get_head_symbol_ids(self) -> frozenset[str]:
        """Get symbol IDs from the head repository model."""
        return self._head_symbol_ids

    def symbol_exists_in_base(self, symbol_id: str) -> bool:
        """Check if a symbol exists in the base repository."""
        return symbol_id in self._base_symbol_ids

    def symbol_exists_in_head(self, symbol_id: str) -> bool:
        """Check if a symbol exists in the head repository."""
        return symbol_id in self._head_symbol_ids
