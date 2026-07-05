"""Evidence models — deterministic facts produced by the core engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class EvidenceCategory(Enum):
    """Categories of evidence produced by the core engine."""

    SIGNAL = auto()
    EXECUTION = auto()
    COVERAGE = auto()
    ARCHITECTURE = auto()
    COMBINED = auto()


@dataclass
class Signal:
    """A low-level deterministic signal produced by a rule.

    Signals are the direct output of rules. They represent
    specific, atomic facts about the changes.
    """

    name: str  # e.g., "ValidationModified", "PersistenceWriteAdded"
    rule_name: str  # Which rule produced this signal
    description: str
    node_ids: List[str] = field(default_factory=list)  # Nodes involved
    edge_ids: List[str] = field(default_factory=list)  # Edges involved
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0  # Always 1.0 for direct signals

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "rule_name": self.rule_name,
            "description": self.description,
            "node_ids": self.node_ids,
            "edge_ids": self.edge_ids,
            "properties": self.properties,
            "confidence": self.confidence,
        }


@dataclass
class ExecutionPath:
    """A path through the call graph from entrypoint to sink."""

    path_id: str
    entrypoint: str  # Node ID
    sink: str  # Node ID
    nodes: List[str] = field(default_factory=list)  # Ordered node IDs
    edges: List[str] = field(default_factory=list)  # Ordered edge IDs
    affected_reads: List[str] = field(default_factory=list)
    affected_writes: List[str] = field(default_factory=list)
    affected_services: List[str] = field(default_factory=list)
    count: int = 1  # Deduplication count

    def to_dict(self) -> dict:
        return {
            "path_id": self.path_id,
            "entrypoint": self.entrypoint,
            "sink": self.sink,
            "nodes": self.nodes,
            "edges": self.edges,
            "affected_reads": self.affected_reads,
            "affected_writes": self.affected_writes,
            "affected_services": self.affected_services,
            "count": self.count,
        }


@dataclass
class Evidence:
    """Base evidence object with deterministic confidence."""

    description: str
    category: EvidenceCategory = EvidenceCategory.SIGNAL
    signals: List[Signal] = field(default_factory=list)
    confidence: float = 1.0
    node_ids: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "category": self.category.name,
            "description": self.description,
            "signals": [s.to_dict() for s in self.signals],
            "confidence": self.confidence,
            "node_ids": self.node_ids,
            "edge_ids": self.edge_ids,
            "properties": self.properties,
        }


@dataclass
class ExecutionEvidence(Evidence):
    """Evidence about execution paths through the changed code."""

    paths: List[ExecutionPath] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.category = EvidenceCategory.EXECUTION

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["paths"] = [p.to_dict() for p in self.paths]
        return base


@dataclass
class CoverageEvidence(Evidence):
    """Evidence about test coverage of changed code."""

    untested_entrypoints: List[str] = field(default_factory=list)
    untested_persistence_paths: List[str] = field(default_factory=list)
    untested_validation: List[str] = field(default_factory=list)
    untested_transactions: List[str] = field(default_factory=list)
    untested_migrations: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.category = EvidenceCategory.COVERAGE

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["untested_entrypoints"] = self.untested_entrypoints
        base["untested_persistence_paths"] = self.untested_persistence_paths
        base["untested_validation"] = self.untested_validation
        base["untested_transactions"] = self.untested_transactions
        base["untested_migrations"] = self.untested_migrations
        return base


@dataclass
class ArchitectureEvidence(Evidence):
    """Evidence about structural/architectural changes."""

    new_dependencies: List[str] = field(default_factory=list)
    removed_dependencies: List[str] = field(default_factory=list)
    new_database_access: List[str] = field(default_factory=list)
    new_events: List[str] = field(default_factory=list)
    new_apis: List[str] = field(default_factory=list)
    new_service_calls: List[str] = field(default_factory=list)
    new_cache_access: List[str] = field(default_factory=list)
    cross_domain_interactions: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.category = EvidenceCategory.ARCHITECTURE

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["new_dependencies"] = self.new_dependencies
        base["removed_dependencies"] = self.removed_dependencies
        base["new_database_access"] = self.new_database_access
        base["new_events"] = self.new_events
        base["new_apis"] = self.new_apis
        base["new_service_calls"] = self.new_service_calls
        base["new_cache_access"] = self.new_cache_access
        base["cross_domain_interactions"] = self.cross_domain_interactions
        return base


@dataclass
class CombinedEvidence(Evidence):
    """Higher-level evidence formed by combining multiple signals."""

    source_signals: List[Signal] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.category = EvidenceCategory.COMBINED

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["source_signals"] = [s.to_dict() for s in self.source_signals]
        return base