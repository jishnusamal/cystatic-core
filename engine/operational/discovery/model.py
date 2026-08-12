"""Discovery IR — the canonical intermediate representation for engineering discoveries.

The Discovery IR is the public contract between deterministic compilation and presentation.

Rules:
1. Every Discovery represents a deterministic engineering insight.
2. Every Discovery has a complete natural-language statement.
3. Evidence supports the statement — evidence never replaces it.
4. The Discovery IR contains no rendering information (no markdown, HTML, GitHub formatting).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DiscoveryKind(str, Enum):
    """Classification of discovery type.

    Each kind represents a distinct category of engineering insight.
    Kinds determine how discoveries are grouped, ordered, and presented.
    """
    HIDDEN_RELATIONSHIP = "hidden_relationship"
    DOMINANT_EXECUTION = "dominant_execution"
    BOUNDARY_INVARIANT = "boundary_invariant"
    VALIDATION_GAP = "validation_gap"
    SHARED_EXECUTION = "shared_execution"
    CROSS_SERVICE = "cross_service"
    PROPAGATION = "propagation"
    FAN_IN = "fan_in"
    FAN_OUT = "fan_out"
    EXECUTION_DEPTH = "execution_depth"
    API_SURFACE = "api_surface"
    EVENT_PROPAGATION = "event_propagation"
    DATA_PROPAGATION = "data_propagation"
    SURPRISE = "surprise"
    COMPRESSED = "compressed"


@dataclass(frozen=True)
class DiscoveryEvidence:
    """A single piece of evidence backing a discovery.

    Always traceable to a compiler artifact location.
    Evidence supports the discovery statement — it never replaces it.

    Attributes:
        source: Compiler stage that produced this evidence ("behavior", "operational", "change").
        source_id: Stable identifier in that stage.
        description: Human-readable description of the evidence.
        evidence_ref: URI to the underlying compiler artifact.
    """
    source: str
    source_id: str
    description: str
    evidence_ref: str = ""


@dataclass(frozen=True)
class DiscoverySupport:
    """Deterministic backing data for a discovery.

    Contains the raw measurements that justify the discovery statement.
    Every field is directly traceable to compiler evidence.

    Metrics support discoveries. Metrics are not discoveries.
    """
    # Core measurements
    execution_reach: int = 0
    fan_in: int = 0
    fan_out: int = 0
    propagation_depth: int = 0
    boundary_crossings: int = 0

    # Surface areas
    external_surface: int = 0
    data_surface: int = 0
    event_surface: int = 0
    validation_coverage: int = 0
    validation_gaps: int = 0

    # Coupling
    shared_by_count: int = 0
    cross_service_count: int = 0

    # Change context
    changed_symbol_count: int = 0
    changed_file_count: int = 0

    # Ranking vector (lexicographic ORDER BY components)
    ranking_vector: tuple[int, ...] = field(default_factory=tuple)

    # Surprise vector (ratios)
    surprise_ratios: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Discovery:
    """A single engineering discovery emitted by the Discovery Compiler.

    The statement must already express the discovery in natural language.
    Evidence supports discoveries — evidence is NOT the discovery.

    Good statement:
        "CustomerWithMembers is reachable from five REST endpoints."

    Bad statement:
        "Reachable Units: 315"

    Attributes:
        id: Stable identifier for this discovery.
        kind: Semantic kind of discovery.
        statement: Complete natural-language statement expressing the discovery.
        importance: Normalized importance score (0.0 to 1.0).
        support: Deterministic backing data for the discovery.
        evidence: Traceable evidence supporting the statement.
        metadata: Additional structured data.
    """
    id: str
    kind: DiscoveryKind
    statement: str
    importance: float = 0.0
    support: DiscoverySupport = field(default_factory=DiscoverySupport)
    evidence: tuple[DiscoveryEvidence, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Normalize mutable defaults to immutable types."""
        if isinstance(self.evidence, list):
            object.__setattr__(self, 'evidence', tuple(self.evidence))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))
        if self.importance < 0.0 or self.importance > 1.0:
            raise ValueError(f"Importance must be in [0.0, 1.0], got {self.importance}")


@dataclass(frozen=True)
class DiscoverySummary:
    """Summary statistics for a set of discoveries."""
    total_discoveries: int = 0
    hidden_relationships: int = 0
    dominant_executions: int = 0
    boundary_invariants: int = 0
    validation_gaps: int = 0
    shared_executions: int = 0
    cross_service: int = 0
    compressed_groups: int = 0
    highest_importance: float = 0.0


@dataclass(frozen=True)
class DiscoveryMetadata:
    """Metadata about the discovery compilation."""
    compiler_version: str = "1.0.0"
    compiled_at: str = ""
    discovery_count: int = 0
    evidence_count: int = 0
    pass_count: int = 0


@dataclass(frozen=True)
class DiscoveryIR:
    """The canonical discovery intermediate representation.

    Contains all deterministic discoveries about a code change.
    The Presentation Compiler consumes this IR and produces
    platform-specific output without performing any analysis.

    Attributes:
        metadata: Metadata about this compilation.
        discoveries: All discoveries, ordered by importance descending.
        summary: Summary statistics.
        evidence_index: All evidence indexed by discovery ID.
    """
    metadata: DiscoveryMetadata
    discoveries: tuple[Discovery, ...] = field(default_factory=tuple)
    summary: DiscoverySummary = field(default_factory=DiscoverySummary)
    evidence_index: dict[str, tuple[DiscoveryEvidence, ...]] = field(default_factory=dict)

    def __post_init__(self):
        """Normalize mutable defaults to immutable types."""
        if isinstance(self.discoveries, list):
            object.__setattr__(self, 'discoveries', tuple(self.discoveries))
        if isinstance(self.evidence_index, dict):
            object.__setattr__(self, 'evidence_index', dict(self.evidence_index))

    def get_discoveries_by_kind(self, kind: DiscoveryKind) -> tuple[Discovery, ...]:
        """Get all discoveries of a specific kind."""
        return tuple(d for d in self.discoveries if d.kind == kind)

    def get_discovery_by_id(self, discovery_id: str) -> Discovery | None:
        """Get a discovery by its identifier."""
        for d in self.discoveries:
            if d.id == discovery_id:
                return d
        return None

    def get_evidence_for(self, discovery_id: str) -> tuple[DiscoveryEvidence, ...]:
        """Get all evidence for a specific discovery."""
        return self.evidence_index.get(discovery_id, ())