"""Behavior model - represents an independently executable workflow."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from engine.repository.model import Evidence


class BehaviorKind(str, Enum):
    """Type of behavior entry point."""
    REST_ENDPOINT = "rest_endpoint"
    GRAPHQL_RESOLVER = "graphql_resolver"
    RPC_HANDLER = "rpc_handler"
    CLI_COMMAND = "cli_command"
    SCHEDULED_JOB = "scheduled_job"
    WORKER_ENTRY = "worker_entry"
    EVENT_CONSUMER = "event_consumer"


@dataclass(frozen=True)
class Behavior:
    """
    Represents an independently executable behavioral unit.

    A behavior is the smallest executable unit of work, such as an
    HTTP request handler, a worker job, a scheduled task, etc.

    Attributes:
        id: Stable identifier for this behavior
        name: Human-readable name
        kind: The type of behavioral unit
        entry_point: The route or trigger identifier (e.g., "POST /checkout")
        root_symbol_id: Symbol id of the entry point handler
        changed_symbol_ids: Symbol ids of changed symbols within this behavior
        evidence: Provenance evidence for this behavior
        metadata: Additional metadata
    """
    id: str
    name: str
    kind: BehaviorKind
    entry_point: str
    root_symbol_id: str
    changed_symbol_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence: Evidence | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate behavior after initialization."""
        if not self.id:
            raise ValueError("Behavior id cannot be empty")
        if not self.name:
            raise ValueError("Behavior name cannot be empty")
        if not self.entry_point:
            raise ValueError("Entry point cannot be empty")
        if not self.root_symbol_id:
            raise ValueError("Root symbol id cannot be empty")
        if isinstance(self.changed_symbol_ids, list):
            object.__setattr__(self, 'changed_symbol_ids', tuple(self.changed_symbol_ids))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))