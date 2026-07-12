"""Graph models for repository compilation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntryPointKind(str, Enum):
    """Type of entry point."""
    REST_ENDPOINT = "rest_endpoint"
    GRAPHQL_RESOLVER = "graphql_resolver"
    RPC_HANDLER = "rpc_handler"
    CLI_COMMAND = "cli_command"
    SCHEDULED_JOB = "scheduled_job"
    WORKER_ENTRY = "worker_entry"


@dataclass(frozen=True)
class CallEdge:
    """Represents a directed call relationship between symbols."""
    caller_id: str
    callee_id: str
    call_type: str = "direct"  # direct, indirect, dynamic
    
    def __post_init__(self):
        """Validate call edge after initialization."""
        if not self.caller_id:
            raise ValueError("Caller id cannot be empty")
        if not self.callee_id:
            raise ValueError("Callee id cannot be empty")


@dataclass(frozen=True)
class EntryPoint:
    """Represents an externally reachable entry point."""
    kind: EntryPointKind
    route: str  # e.g., "POST /checkout"
    handler_id: str  # Symbol id of the handler
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate entry point after initialization."""
        if not self.route:
            raise ValueError("Route cannot be empty")
        if not self.handler_id:
            raise ValueError("Handler id cannot be empty")


@dataclass(frozen=True)
class CallGraph:
    """Directed graph of function/method calls."""
    edges: tuple[CallEdge, ...] = field(default_factory=tuple)
    
    def __post_init__(self):
        """Validate call graph after initialization."""
        # Convert list to tuple if needed
        if isinstance(self.edges, list):
            object.__setattr__(self, 'edges', tuple(self.edges))


@dataclass(frozen=True)
class ReferenceGraph:
    """Graph of symbol-to-symbol references (imports, inheritance, etc.)."""
    edges: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    # (source_id, target_id, relationship_type)
    # relationship_type: "imports", "inherits", "implements", "references"
    
    def __post_init__(self):
        """Validate reference graph after initialization."""
        if isinstance(self.edges, list):
            object.__setattr__(self, 'edges', tuple(self.edges))
        for edge in self.edges:
            if len(edge) != 3:
                raise ValueError(f"Invalid reference edge: {edge}")