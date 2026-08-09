"""Discovery Model - the canonical intermediate representation for deterministic discoveries.

The Discovery Model contains only deterministic engineering observations.
No English summaries, no ranking, no significance scores, no presentation metadata.

Schema:
    id: Stable identifier
    kind: Discovery type
    facts: Structured deterministic data
    references: Traceable references to compiler artifacts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DiscoveryKind(str, Enum):
    """Classification of discovery type.
    
    Each kind represents a distinct category of deterministic engineering insight.
    """
    SHARED_EXECUTION = "shared_execution"
    VALIDATION_GAP = "validation_gap"
    BOUNDARY_CROSSING = "boundary_crossing"
    HIDDEN_RELATIONSHIP = "hidden_relationship"
    DEEP_EXECUTION = "deep_execution"
    SHARED_DEPENDENCY = "shared_dependency"
    EVENT_PUBLICATION = "event_publication"
    STATE_MUTATION = "state_mutation"
    PUBLIC_INTERFACE_CHANGE = "public_interface_change"


@dataclass(frozen=True)
class DiscoveryReference:
    """Traceable reference back to a compiler artifact.
    
    Attributes:
        artifact_type: Type of compiler artifact (e.g., "behavior", "operational", "change").
        artifact_id: Stable identifier of the artifact.
        location: Optional location string (e.g., file path, symbol ID).
    """
    artifact_type: str = ""
    artifact_id: str = ""
    location: str = ""


@dataclass(frozen=True)
class DiscoveryFact:
    """Structured deterministic data for a discovery.
    
    Different discovery kinds populate different fields.
    All fields are optional - only relevant fields are populated.
    
    Shared Execution:
        shared_symbol_ids: Symbols shared across behaviors
        behavior_count: Number of behaviors sharing execution
        
    Validation Gap:
        untested_symbol_ids: Symbols without test coverage
        validation_coverage_ratio: Ratio of tested to total symbols
        
    Boundary Crossing:
        crossed_boundaries: List of boundary crossings
        service_transitions: Number of service transitions
        
    Hidden Relationship:
        related_symbol_pairs: Pairs of related symbols
        relationship_type: Type of relationship
        
    Deep Execution:
        max_depth: Maximum execution depth
        deep_paths: List of deep execution paths
        
    Shared Dependency:
        shared_dependencies: List of shared dependencies
        dependency_count: Number of shared dependencies
        
    Event Publication:
        published_events: List of published events
        event_handlers: List of event handlers
        
    State Mutation:
        mutated_state: List of state mutations
        mutation_sources: Sources of mutations
        
    Public Interface Change:
        changed_interfaces: List of changed public interfaces
        interface_types: Types of interfaces changed
    """
    # Shared Execution
    shared_symbol_ids: tuple[str, ...] = field(default_factory=tuple)
    behavior_count: int = 0
    
    # Validation Gap
    untested_symbol_ids: tuple[str, ...] = field(default_factory=tuple)
    validation_coverage_ratio: float = 0.0
    
    # Boundary Crossing
    crossed_boundaries: tuple[str, ...] = field(default_factory=tuple)
    service_transitions: int = 0
    
    # Hidden Relationship
    related_symbol_pairs: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    relationship_type: str = ""
    
    # Deep Execution
    max_depth: int = 0
    deep_paths: tuple[str, ...] = field(default_factory=tuple)
    
    # Shared Dependency
    shared_dependencies: tuple[str, ...] = field(default_factory=tuple)
    dependency_count: int = 0
    
    # Event Publication
    published_events: tuple[str, ...] = field(default_factory=tuple)
    event_handlers: tuple[str, ...] = field(default_factory=tuple)
    
    # State Mutation
    mutated_state: tuple[str, ...] = field(default_factory=tuple)
    mutation_sources: tuple[str, ...] = field(default_factory=tuple)
    
    # Public Interface Change
    changed_interfaces: tuple[str, ...] = field(default_factory=tuple)
    interface_types: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Discovery:
    """A single deterministic engineering discovery.
    
    Attributes:
        id: Stable identifier for this discovery.
        kind: Type of discovery.
        facts: Structured deterministic data.
        references: Traceable references to compiler artifacts.
    """
    id: str = ""
    kind: DiscoveryKind = DiscoveryKind.SHARED_EXECUTION
    facts: DiscoveryFact = field(default_factory=DiscoveryFact)
    references: tuple[DiscoveryReference, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiscoveryModel:
    """The canonical model for all deterministic engineering discoveries.
    
    This model is produced by the Discovery Compiler and consumed by ReviewContext.
    It contains no presentation logic, no ranking, no summaries.
    
    Attributes:
        discoveries: All discoveries emitted by discovery passes.
        metadata: Compilation metadata (version, timestamp, counts).
    """
    discoveries: tuple[Discovery, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Normalize mutable defaults to immutable types."""
        if isinstance(self.discoveries, list):
            object.__setattr__(self, 'discoveries', tuple(self.discoveries))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))
    
    def get_discoveries_by_kind(self, kind: DiscoveryKind) -> tuple[Discovery, ...]:
        """Get all discoveries of a specific kind."""
        return tuple(d for d in self.discoveries if d.kind == kind)
    
    def get_discovery_by_id(self, discovery_id: str) -> Discovery | None:
        """Get a discovery by its identifier."""
        for d in self.discoveries:
            if d.id == discovery_id:
                return d
        return None