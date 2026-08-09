"""Engineering Discovery Model - the final immutable IR for change analysis.

This is the canonical artifact that renderers and AI consume.
It is a composition of all deterministic models produced by the compilation pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.behavior.model import (
    Behavior,
    BehaviorModel,
    ExecutionUnit,
    ExecutionChain,
    EntryPoint,
    TerminalPoint,
    SharedExecution,
)
from engine.change.model import ChangeModel
from engine.repository.model import RepositoryModel


@dataclass(frozen=True)
class EngineeringDiscoveryModel:
    """
    The canonical immutable IR produced by the compiler.

    This is a deterministic, immutable composition of all compiler outputs.
    It answers: "What execution exists? What is reachable? What is shared?"

    The model is organized for deterministic consumption, not human presentation.
    Every downstream consumer (GitHub, Slack, Dashboard, API, LLM) renders
    or interprets this same model.

    Attributes:
        repository: Repository model (what the repo contains).
        change: Change model (what exactly changed).
        behavior: Behavior model (what behavior is affected).
        operational: Full OperationalChangeModel context (preserved for enrichment).

        execution_units: All execution units across all behaviors.
        execution_chains: Ordered execution chains for each behavior.
        entry_points: Where execution begins.
        terminal_points: Where execution ends.
        shared_executions: Infrastructure shared across behaviors.
        reachable_units: Execution units reachable from changed symbols.
        execution_depth: Maximum execution depth across all behaviors.

        dependency: Dependency model (structural dependencies).
        data: Data model (persistent state affected).
        event: Event model (async interactions).
        api: API model (externally visible interfaces).
        validation: Validation model (test evidence).
        metrics: Discovery metrics (observable metrics).
    """

    # Core models
    repository: RepositoryModel
    change: ChangeModel
    behavior: BehaviorModel

    # Full operational context (preserved for renderers and AI)
    operational: object | None = field(default=None, compare=False)

    # Execution-oriented abstractions
    execution_units: tuple[ExecutionUnit, ...] = field(default_factory=tuple)
    execution_chains: tuple[ExecutionChain, ...] = field(default_factory=tuple)
    entry_points: tuple[EntryPoint, ...] = field(default_factory=tuple)
    terminal_points: tuple[TerminalPoint, ...] = field(default_factory=tuple)
    shared_executions: tuple[SharedExecution, ...] = field(default_factory=tuple)
    reachable_units: tuple[ExecutionUnit, ...] = field(default_factory=tuple)
    execution_depth: int = 0

    # Enrichment models
    dependency: object | None = field(default=None, compare=False)
    data: object | None = field(default=None, compare=False)
    event: object | None = field(default=None, compare=False)
    api: object | None = field(default=None, compare=False)
    validation: object | None = field(default=None, compare=False)
    metrics: object | None = field(default=None, compare=False)

    def __post_init__(self):
        """Validate and convert mutable defaults to immutable types."""
        if isinstance(self.execution_units, list):
            object.__setattr__(self, 'execution_units', tuple(self.execution_units))
        if isinstance(self.execution_chains, list):
            object.__setattr__(self, 'execution_chains', tuple(self.execution_chains))
        if isinstance(self.entry_points, list):
            object.__setattr__(self, 'entry_points', tuple(self.entry_points))
        if isinstance(self.terminal_points, list):
            object.__setattr__(self, 'terminal_points', tuple(self.terminal_points))
        if isinstance(self.shared_executions, list):
            object.__setattr__(self, 'shared_executions', tuple(self.shared_executions))
        if isinstance(self.reachable_units, list):
            object.__setattr__(self, 'reachable_units', tuple(self.reachable_units))
        # Validate core models are present
        if self.repository is None:
            raise ValueError("repository model is required")
        if self.change is None:
            raise ValueError("change model is required")
        if self.behavior is None:
            raise ValueError("behavior model is required")

    def has_all_required_models(self) -> bool:
        """Check that all required models (repository, change, behavior) are present."""
        return (
            self.repository is not None
            and self.change is not None
            and self.behavior is not None
        )

    def has_operational_model(self) -> bool:
        """Check if an OperationalChangeModel is present."""
        return self.operational is not None

    def has_dependency_model(self) -> bool:
        """Check if a dependency model is present."""
        return self.dependency is not None

    def has_data_model(self) -> bool:
        """Check if a data model is present."""
        return self.data is not None

    def has_event_model(self) -> bool:
        """Check if an event model is present."""
        return self.event is not None

    def has_api_model(self) -> bool:
        """Check if an API model is present."""
        return self.api is not None

    def has_validation_model(self) -> bool:
        """Check if a validation model is present."""
        return self.validation is not None

    def has_metrics_model(self) -> bool:
        """Check if a metrics model is present."""
        return self.metrics is not None

    @property
    def populated_optional_models(self) -> tuple[str, ...]:
        """Get the names of all populated optional models."""
        models: list[str] = []
        if self.has_operational_model():
            models.append("operational")
        if self.has_dependency_model():
            models.append("dependency")
        if self.has_data_model():
            models.append("data")
        if self.has_event_model():
            models.append("event")
        if self.has_api_model():
            models.append("api")
        if self.has_validation_model():
            models.append("validation")
        if self.has_metrics_model():
            models.append("metrics")
        return tuple(models)

    def get_behaviors(self) -> tuple[Behavior, ...]:
        """Get all behaviors from the behavior model."""
        return self.behavior.behaviors

    def get_execution_units_for_behavior(self, behavior_id: str) -> tuple[ExecutionUnit, ...]:
        """Get all execution units for a specific behavior."""
        return tuple(
            u for u in self.execution_units
            if u.id.startswith(f"unit://{behavior_id}")
        )

    def get_reachable_units_for_behavior(self, behavior_id: str) -> tuple[ExecutionUnit, ...]:
        """Get all reachable units for a specific behavior."""
        return tuple(
            u for u in self.reachable_units
            if u.id.startswith(f"reachable://{behavior_id}")
        )

    def __repr__(self) -> str:
        """Human-readable representation showing which models are present."""
        parts = ["EngineeringDiscoveryModel"]
        parts.append(f"  repository: {type(self.repository).__name__}")
        parts.append(f"  change:     {type(self.change).__name__}")
        parts.append(f"  behavior:   {type(self.behavior).__name__}")
        parts.append(f"  execution_units: {len(self.execution_units)}")
        parts.append(f"  execution_chains: {len(self.execution_chains)}")
        parts.append(f"  entry_points: {len(self.entry_points)}")
        parts.append(f"  terminal_points: {len(self.terminal_points)}")
        parts.append(f"  shared_executions: {len(self.shared_executions)}")
        parts.append(f"  reachable_units: {len(self.reachable_units)}")
        parts.append(f"  execution_depth: {self.execution_depth}")
        optional = self.populated_optional_models
        if optional:
            for name in optional:
                parts.append(f"  {name}:    present")
        else:
            parts.append("  (no optional models)")
        return "\n".join(parts)


# Backward compatibility alias
EngineeringDiscoveryArtifact = EngineeringDiscoveryModel