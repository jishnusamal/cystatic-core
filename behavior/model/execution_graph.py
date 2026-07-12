"""Execution graph model - a bounded projection of the repository call graph."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecutionNode:
    """
    Represents a single node in an execution graph.

    Each node corresponds to a symbol that is executed as part of
    a behavior's execution path.

    Attributes:
        symbol_id: The symbol id this node represents
        order: Execution order (topological position)
    """
    symbol_id: str
    order: int

    def __post_init__(self):
        """Validate execution node after initialization."""
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")
        if self.order < 0:
            raise ValueError(f"Order cannot be negative: {self.order}")


@dataclass(frozen=True)
class ExecutionEdge:
    """
    Represents a directed call relationship within an execution graph.

    Attributes:
        caller_id: Symbol id of the caller
        callee_id: Symbol id of the callee
        call_type: Type of call (direct, indirect, dynamic)
    """
    caller_id: str
    callee_id: str
    call_type: str = "direct"

    def __post_init__(self):
        """Validate execution edge after initialization."""
        if not self.caller_id:
            raise ValueError("Caller id cannot be empty")
        if not self.callee_id:
            raise ValueError("Callee id cannot be empty")


@dataclass(frozen=True)
class ExecutionGraph:
    """
    A bounded projection of the repository call graph rooted at a behavior.

    Unlike the repository-wide call graph, an execution graph only contains
    the symbols reachable from a specific behavior's entry point.

    Attributes:
        behavior_id: The behavior this graph belongs to
        nodes: Execution nodes in this graph
        edges: Execution edges in this graph
    """
    behavior_id: str
    nodes: tuple[ExecutionNode, ...] = field(default_factory=tuple)
    edges: tuple[ExecutionEdge, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Validate execution graph after initialization."""
        if not self.behavior_id:
            raise ValueError("Behavior id cannot be empty")
        if isinstance(self.nodes, list):
            object.__setattr__(self, 'nodes', tuple(self.nodes))
        if isinstance(self.edges, list):
            object.__setattr__(self, 'edges', tuple(self.edges))

    def get_node_ids(self) -> tuple[str, ...]:
        """Get all symbol ids in this execution graph."""
        return tuple(n.symbol_id for n in self.nodes)

    def get_edges_for(self, symbol_id: str) -> tuple[ExecutionEdge, ...]:
        """Get all edges where this symbol is the caller."""
        return tuple(e for e in self.edges if e.caller_id == symbol_id)

    def get_called_by(self, symbol_id: str) -> tuple[ExecutionEdge, ...]:
        """Get all edges where this symbol is the callee."""
        return tuple(e for e in self.edges if e.callee_id == symbol_id)
