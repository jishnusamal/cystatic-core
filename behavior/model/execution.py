"""Execution model - represents execution-oriented abstractions.

This module defines the core execution concepts:
- ExecutionUnit: An atomic unit of execution (e.g., "Checkout Confirmation")
- ExecutionChain: A sequence of execution units
- EntryPoint: Where execution begins
- TerminalPoint: Where execution ends
- SharedExecution: Infrastructure shared across execution units
"""

from dataclasses import dataclass, field
from typing import Any

from language_adapters.model import Evidence


@dataclass(frozen=True)
class ExecutionUnit:
    """
    An atomic unit of execution within a behavior.

    An execution unit represents a single, coherent step in the execution flow,
    such as "Validate Discount", "Process Payment", "Send Notification".

    Attributes:
        id: Stable identifier for this execution unit
        name: Human-readable name (e.g., "Discount Validation")
        symbol_id: The symbol that implements this execution unit
        order: Position in the execution chain (0-based)
        evidence: Provenance evidence for this unit
        metadata: Additional metadata
    """
    id: str
    name: str
    symbol_id: str
    order: int
    evidence: Evidence | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate execution unit after initialization."""
        if not self.id:
            raise ValueError("Execution unit id cannot be empty")
        if not self.name:
            raise ValueError("Execution unit name cannot be empty")
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")
        if self.order < 0:
            raise ValueError(f"Order cannot be negative: {self.order}")
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))


@dataclass(frozen=True)
class ExecutionChain:
    """
    A sequence of execution units representing a complete execution flow.

    An execution chain is the ordered path from an entry point through
    all reachable execution units within a behavior.

    Attributes:
        id: Stable identifier for this chain
        behavior_id: The behavior this chain belongs to
        units: Ordered execution units in this chain
        evidence: Provenance evidence for this chain
    """
    id: str
    behavior_id: str
    units: tuple[ExecutionUnit, ...] = field(default_factory=tuple)
    evidence: Evidence | None = None

    def __post_init__(self):
        """Validate execution chain after initialization."""
        if not self.id:
            raise ValueError("Execution chain id cannot be empty")
        if not self.behavior_id:
            raise ValueError("Behavior id cannot be empty")
        if isinstance(self.units, list):
            object.__setattr__(self, 'units', tuple(self.units))

    def get_unit_ids(self) -> tuple[str, ...]:
        """Get all symbol ids in this execution chain."""
        return tuple(u.symbol_id for u in self.units)

    def get_max_depth(self) -> int:
        """Get the maximum execution depth (number of units - 1)."""
        return max((u.order for u in self.units), default=0)


@dataclass(frozen=True)
class EntryPoint:
    """
    Where execution begins.

    An entry point is the starting symbol of an execution chain,
    typically an HTTP handler, worker entry, or scheduled job.

    Attributes:
        id: Stable identifier for this entry point
        behavior_id: The behavior this entry point belongs to
        symbol_id: The symbol that is the entry point
        kind: The type of entry point (REST, GraphQL, RPC, etc.)
        route: The route or trigger identifier
        evidence: Provenance evidence for this entry point
    """
    id: str
    behavior_id: str
    symbol_id: str
    kind: str
    route: str
    evidence: Evidence | None = None

    def __post_init__(self):
        """Validate entry point after initialization."""
        if not self.id:
            raise ValueError("Entry point id cannot be empty")
        if not self.behavior_id:
            raise ValueError("Behavior id cannot be empty")
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")
        if not self.route:
            raise ValueError("Route cannot be empty")


@dataclass(frozen=True)
class TerminalPoint:
    """
    Where execution ends.

    A terminal point is a symbol that does not call any other symbols
    within the execution graph, or is a known terminal (return, response, etc.).

    Attributes:
        id: Stable identifier for this terminal point
        behavior_id: The behavior this terminal point belongs to
        symbol_id: The symbol that is the terminal point
        kind: The type of terminal (return, response, error, etc.)
        evidence: Provenance evidence for this terminal point
    """
    id: str
    behavior_id: str
    symbol_id: str
    kind: str = "return"
    evidence: Evidence | None = None

    def __post_init__(self):
        """Validate terminal point after initialization."""
        if not self.id:
            raise ValueError("Terminal point id cannot be empty")
        if not self.behavior_id:
            raise ValueError("Behavior id cannot be empty")
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")


@dataclass(frozen=True)
class SharedExecution:
    """
    Infrastructure shared across multiple execution units.

    Shared execution represents symbols that are used by multiple behaviors
    or multiple execution units within a behavior.

    Attributes:
        id: Stable identifier for this shared execution
        symbol_id: The shared symbol
        used_by: List of behavior IDs that use this shared execution
        evidence: Provenance evidence for this shared execution
    """
    id: str
    symbol_id: str
    used_by: tuple[str, ...] = field(default_factory=tuple)
    evidence: Evidence | None = None

    def __post_init__(self):
        """Validate shared execution after initialization."""
        if not self.id:
            raise ValueError("Shared execution id cannot be empty")
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")
        if isinstance(self.used_by, list):
            object.__setattr__(self, 'used_by', tuple(self.used_by))