"""Base classes for behavior compiler passes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from engine.behavior.model import (
    ExecutionUnit,
    ExecutionChain,
    EntryPoint,
    TerminalPoint,
    SharedExecution,
)


@dataclass
class BehaviorPassContext:
    """
    Context passed between behavior compiler passes.

    This is a mutable container that accumulates state as passes execute.
    """

    # Pass 1 output: Discovered behaviors
    behaviors: list = field(default_factory=list)

    # Pass 2 output: Execution graphs
    execution_graphs: list = field(default_factory=list)

    # Pass 3 output: Execution chains (ordered execution units)
    execution_chains: list = field(default_factory=list)

    # Pass 4 output: Entry points
    entry_points: list = field(default_factory=list)

    # Pass 5 output: Terminal points
    terminal_points: list = field(default_factory=list)

    # Pass 6 output: Shared executions
    shared_executions: list = field(default_factory=list)

    # Pass 7 output: Reachable units
    reachable_units: list = field(default_factory=list)

    # Indices for fast lookup during compilation
    symbol_to_behaviors: dict[str, list] = field(default_factory=dict)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class BehaviorCompilerPass(ABC):
    """
    Base class for all behavior compiler passes.

    Each pass has a single responsibility and transforms the context
    for the next pass in the pipeline.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this pass."""
        pass

    @abstractmethod
    def run(self, context: BehaviorPassContext) -> BehaviorPassContext:
        """
        Execute the pass and return updated context.

        Args:
            context: The current pass context

        Returns:
            Updated pass context
        """
        pass

    def validate_input(self, context: BehaviorPassContext) -> bool:
        """
        Validate that the context has required inputs for this pass.

        Override in subclasses to add validation logic.
        """
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
