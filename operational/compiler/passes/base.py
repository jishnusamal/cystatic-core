"""Base classes for operational compiler passes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from behavior.model import BehaviorModel
from change.model import ChangeModel, RepositoryDelta
from language_adapters.model import RepositoryModel
from operational.model import OperationalChangeModel


@dataclass
class OperationalPassContext:
    """
    Context passed between operational compiler passes.

    This is a mutable container that accumulates state as passes execute.
    """

    # Input models (set before first pass)
    repository_model: RepositoryModel | None = None
    repository_delta: RepositoryDelta | None = None
    change_model: ChangeModel | None = None
    behavior_model: BehaviorModel | None = None

    # Composition outputs
    composed_model: OperationalChangeModel | None = None
    consistency_errors: list[str] = field(default_factory=list)

    # Enrichment analysis outputs (cached for pass chaining)
    dependency_model: object | None = None
    data_model: object | None = None
    event_model: object | None = None
    api_model: object | None = None
    validation_model: object | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_consistency_errors(self) -> bool:
        """Check if any consistency errors were found."""
        return len(self.consistency_errors) > 0

    @property
    def discovery_metrics(self) -> Any | None:
        """Get discovery metrics from metadata if present."""
        return self.metadata.get("discovery_metrics")


class OperationalCompilerPass(ABC):
    """
    Base class for all operational compiler passes.

    Each pass has a single responsibility and transforms the context
    for the next pass in the pipeline.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this pass."""
        pass

    @abstractmethod
    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Execute the pass and return updated context.

        Args:
            context: The current pass context

        Returns:
            Updated pass context
        """
        pass

    def validate_input(self, context: OperationalPassContext) -> bool:
        """
        Validate that the context has required inputs for this pass.

        Override in subclasses to add validation logic.
        """
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"