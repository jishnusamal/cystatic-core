"""Behavior model - the output of Phase 3 compilation."""

from dataclasses import dataclass, field

from .behavior import Behavior
from .execution_graph import ExecutionGraph


@dataclass(frozen=True)
class BehaviorModel:
    """
    The complete behavior model produced by Phase 3 compilation.

    This is a deterministic, language-agnostic representation of a pull request
    that answers: "What behavior has changed?"

    The Behavior Model is a reusable intermediate representation that future
    compiler passes (dependency, data, event, validation) build upon.

    Attributes:
        behaviors: All affected behavioral units
        execution_graphs: Execution graphs for each behavior
    """
    behaviors: tuple[Behavior, ...] = field(default_factory=tuple)
    execution_graphs: tuple[ExecutionGraph, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Validate behavior model after initialization."""
        if isinstance(self.behaviors, list):
            object.__setattr__(self, 'behaviors', tuple(self.behaviors))
        if isinstance(self.execution_graphs, list):
            object.__setattr__(self, 'execution_graphs', tuple(self.execution_graphs))

    def get_behavior_by_id(self, behavior_id: str) -> Behavior | None:
        """Get a behavior by its identifier."""
        for behavior in self.behaviors:
            if behavior.id == behavior_id:
                return behavior
        return None

    def get_behaviors_by_kind(self, kind: str) -> tuple[Behavior, ...]:
        """Get all behaviors of a specific kind."""
        return tuple(b for b in self.behaviors if b.kind.value == kind)

    def get_execution_graph(self, behavior_id: str) -> ExecutionGraph | None:
        """Get the execution graph for a specific behavior."""
        for graph in self.execution_graphs:
            if graph.behavior_id == behavior_id:
                return graph
        return None

    def get_affected_behaviors_for_symbol(self, symbol_id: str) -> tuple[Behavior, ...]:
        """Get all behaviors that contain a changed symbol."""
        return tuple(
            b for b in self.behaviors
            if symbol_id in b.changed_symbol_ids
        )