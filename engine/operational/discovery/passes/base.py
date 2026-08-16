"""Base classes for discovery compiler passes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from engine.operational.discovery.model import Discovery, DiscoveryIR
from engine.operational.model import EngineeringDiscoveryModel


@dataclass
class DiscoveryPassContext:
    """Mutable context passed between discovery compiler passes.

    Each pass reads from the EngineeringDiscoveryModel and writes discoveries
    to the discoveries list. The context accumulates state as passes execute.
    """

    # Input: Engineering Discovery Model (immutable, set before first pass)
    discovery_model: EngineeringDiscoveryModel | None = None

    # Accumulated discoveries across all passes
    discoveries: list[Discovery] = field(default_factory=list)

    # Final Discovery IR (set by the compiler after all passes)
    discovery_ir: DiscoveryIR | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def discovery_count(self) -> int:
        """Get the total number of discoveries."""
        return len(self.discoveries)


class DiscoveryCompilerPass(ABC):
    """Base class for all discovery compiler passes.

    Each pass has a single responsibility:
    Read from the EngineeringDiscoveryModel, emit Discovery objects.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this pass."""

    @abstractmethod
    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.

        Args:
            context: The current pass context with discovery_model set.

        Returns:
            Updated pass context with new discoveries appended.
        """

    def validate_input(self, context: DiscoveryPassContext) -> bool:
        """Validate that the context has required inputs for this pass."""
        return context.discovery_model is not None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
