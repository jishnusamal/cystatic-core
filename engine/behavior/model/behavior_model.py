"""Behavior model - identifies affected behaviors from code changes.

This is the execution-oriented behavior model that answers:
"What execution exists? What is reachable? What is shared?"
"""

from dataclasses import dataclass, field

from .behavior import Behavior
from .execution import (
    EntryPoint,
    ExecutionChain,
    ExecutionUnit,
    SharedExecution,
    TerminalPoint,
)
from .execution_graph import ExecutionGraph


@dataclass(frozen=True)
class BehaviorModel:
    """
    The complete behavior model produced by behavior compilation.

    This is a deterministic, language-agnostic representation of a pull request
    that answers: "What execution exists?"

    The Behavior Model is a reusable intermediate representation that future
    compiler passes (dependency, data, event, validation) build upon.

    Attributes:
        behaviors: All affected behavioral units
        execution_graphs: Execution graphs for each behavior (symbol-based)
        execution_chains: Ordered execution chains for each behavior
        entry_points: Where execution begins
        terminal_points: Where execution ends
        shared_executions: Infrastructure shared across behaviors
        reachable_units: Execution units reachable from changed symbols
        execution_depth: Maximum execution depth across all behaviors
    """

    behaviors: tuple[Behavior, ...] = field(default_factory=tuple)
    execution_graphs: tuple[ExecutionGraph, ...] = field(default_factory=tuple)

    # Execution-oriented abstractions
    execution_chains: tuple[ExecutionChain, ...] = field(default_factory=tuple)
    entry_points: tuple[EntryPoint, ...] = field(default_factory=tuple)
    terminal_points: tuple[TerminalPoint, ...] = field(default_factory=tuple)
    shared_executions: tuple[SharedExecution, ...] = field(default_factory=tuple)
    reachable_units: tuple[ExecutionUnit, ...] = field(default_factory=tuple)
    execution_depth: int = 0

    def __post_init__(self):
        """Validate behavior model after initialization."""
        if isinstance(self.behaviors, list):
            object.__setattr__(self, "behaviors", tuple(self.behaviors))
        if isinstance(self.execution_graphs, list):
            object.__setattr__(self, "execution_graphs", tuple(self.execution_graphs))
        if isinstance(self.execution_chains, list):
            object.__setattr__(self, "execution_chains", tuple(self.execution_chains))
        if isinstance(self.entry_points, list):
            object.__setattr__(self, "entry_points", tuple(self.entry_points))
        if isinstance(self.terminal_points, list):
            object.__setattr__(self, "terminal_points", tuple(self.terminal_points))
        if isinstance(self.shared_executions, list):
            object.__setattr__(self, "shared_executions", tuple(self.shared_executions))
        if isinstance(self.reachable_units, list):
            object.__setattr__(self, "reachable_units", tuple(self.reachable_units))

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

    def get_execution_chain(self, behavior_id: str) -> ExecutionChain | None:
        """Get the execution chain for a specific behavior."""
        for chain in self.execution_chains:
            if chain.behavior_id == behavior_id:
                return chain
        return None

    def get_entry_point(self, behavior_id: str) -> EntryPoint | None:
        """Get the entry point for a specific behavior."""
        for ep in self.entry_points:
            if ep.behavior_id == behavior_id:
                return ep
        return None

    def get_terminal_points_for_behavior(
        self, behavior_id: str
    ) -> tuple[TerminalPoint, ...]:
        """Get all terminal points for a specific behavior."""
        return tuple(tp for tp in self.terminal_points if tp.behavior_id == behavior_id)

    def get_affected_behaviors_for_symbol(self, symbol_id: str) -> tuple[Behavior, ...]:
        """Get all behaviors that contain a changed symbol."""
        return tuple(b for b in self.behaviors if symbol_id in b.changed_symbol_ids)

    def get_reachable_units_for_behavior(
        self, behavior_id: str
    ) -> tuple[ExecutionUnit, ...]:
        """Get all reachable execution units for a specific behavior."""
        return tuple(
            ru
            for ru in self.reachable_units
            if ru.id.startswith(f"reachable://{behavior_id}")
        )
