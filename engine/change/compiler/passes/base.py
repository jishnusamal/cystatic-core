"""Base classes for change compiler passes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChangePassContext:
    """
    Context passed between change compiler passes.

    This is a mutable container that accumulates state as passes execute.
    """

    # Input from git diff
    diff_data: dict[str, Any] = field(default_factory=dict)

    # Pass 1 output: Changed symbols
    added_symbols: list = field(default_factory=list)
    removed_symbols: list = field(default_factory=list)
    modified_symbols: list[dict] = field(default_factory=list)
    renamed_symbols: list[dict] = field(default_factory=list)

    # Pass 2 output: Change classification
    symbol_changes: dict[str, list] = field(
        default_factory=dict
    )  # symbol_id -> list of changes
    changed_imports: list[dict] = field(default_factory=list)
    changed_endpoints: list[dict] = field(default_factory=list)

    # Indices for fast lookup
    old_symbol_index: dict[str, Any] = field(default_factory=dict)
    new_symbol_index: dict[str, Any] = field(default_factory=dict)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class ChangeCompilerPass(ABC):
    """
    Base class for all change compiler passes.

    Each pass has a single responsibility and transforms the context
    for the next pass in the pipeline.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this pass."""
        pass

    @abstractmethod
    def run(self, context: ChangePassContext) -> ChangePassContext:
        """
        Execute the pass and return updated context.

        Args:
            context: The current pass context

        Returns:
            Updated pass context
        """
        pass

    def validate_input(self, context: ChangePassContext) -> bool:
        """
        Validate that the context has required inputs for this pass.

        Override in subclasses to add validation logic.
        """
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
