"""Impact Surface model - represents the reachable impact boundary from a change."""

from dataclasses import dataclass, field

from engine.repository.model.repository_model import EntryPoint
from engine.repository.query.types import (
    DatabaseRelationship,
    EventPublication,
)


@dataclass(frozen=True)
class ImpactSurface:
    """
    Represents the calculated impact of code changes, found via bounded traversal.

    Attributes:
        affected_symbols: Set of symbol IDs directly or indirectly affected.
        affected_services: Set of service boundaries crossed.
        affected_endpoints: Endpoints (REST/RPC) reachable from the changes.
        affected_databases: Database resources reachable.
        affected_events: Event publications reachable.
        traversal_evidence: Evidence of traversal paths for reasoning/validation.
    """

    affected_symbols: frozenset[str] = frozenset()
    affected_services: frozenset[str] = frozenset()
    affected_endpoints: frozenset[EntryPoint] = frozenset()
    affected_databases: frozenset[DatabaseRelationship] = frozenset()
    affected_events: frozenset[EventPublication] = frozenset()
    traversal_evidence: tuple[dict[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Ensure collections are frozen/immutable."""
        if isinstance(self.affected_symbols, (set, list)):
            object.__setattr__(
                self, "affected_symbols", frozenset(self.affected_symbols)
            )
        if isinstance(self.affected_services, (set, list)):
            object.__setattr__(
                self, "affected_services", frozenset(self.affected_services)
            )
        if isinstance(self.affected_endpoints, (set, list)):
            object.__setattr__(
                self, "affected_endpoints", frozenset(self.affected_endpoints)
            )
        if isinstance(self.affected_databases, (set, list)):
            object.__setattr__(
                self, "affected_databases", frozenset(self.affected_databases)
            )
        if isinstance(self.affected_events, (set, list)):
            object.__setattr__(self, "affected_events", frozenset(self.affected_events))
        if isinstance(self.traversal_evidence, list):
            object.__setattr__(
                self, "traversal_evidence", tuple(self.traversal_evidence)
            )
