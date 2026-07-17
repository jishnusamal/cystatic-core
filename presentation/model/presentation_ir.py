"""Presentation IR — stable, platform-independent representation for reviewer consumption.

Every statement in the Presentation IR is directly traceable to compiler evidence.
Contains no Markdown, HTML, Slack blocks, or UI-specific formatting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =========================================================================
# Discovery Kind
# =========================================================================

class DiscoveryKind(str, Enum):
    """The kind of a presentation discovery.

    Every discovery extracted from compiler artifacts has exactly one kind.
    Kind determines how the discovery is measured, ranked, visualized, and placed.
    """
    ADDED_SYMBOLS = "added_symbols"
    REMOVED_SYMBOLS = "removed_symbols"
    MODIFIED_SYMBOLS = "modified_symbols"
    CHANGED_ENDPOINTS = "changed_endpoints"
    CHANGED_IMPORTS = "changed_imports"
    EXECUTION_SURFACE = "execution_surface"
    EXECUTION_CHAIN = "execution_chain"
    REACHABLE_UNITS = "reachable_units"
    EXECUTION_DEPTH = "execution_depth"
    BEHAVIOR = "behavior"
    ENTRY_POINT = "entry_point"
    TERMINAL_POINT = "terminal_point"
    SHARED_EXECUTION = "shared_execution"
    API_SURFACE = "api_surface"
    DATA_SURFACE = "data_surface"
    EVENT_SURFACE = "event_surface"
    DEPENDENCY_SURFACE = "dependency_surface"
    VALIDATION_COVERAGE = "validation_coverage"
    VALIDATION_GAP = "validation_gap"
    COMPRESSED = "compressed"


# =========================================================================
# Evidence
# =========================================================================

@dataclass(frozen=True)
class PresentationEvidence:
    """Traceable evidence linking a presentation statement back to compiler evidence.

    Attributes:
        source: The compiler stage that produced this evidence (e.g., "behavior", "change", "operational").
        source_id: The stable identifier of the source fact (e.g., behavior_id, symbol_id).
        description: Brief description of the evidence.
        evidence_ref: Direct reference to underlying compiler artifact.
    """
    source: str
    source_id: str
    description: str
    evidence_ref: str = ""


# =========================================================================
# Significance Metrics (measurements, not scores)
# =========================================================================

@dataclass(frozen=True)
class SignificanceMetrics:
    """Deterministic significance **measurements** for a discovery.

    These are raw measurements — not scores, not weights, not ranks.
    Every metric is directly computed from compiler outputs.

    Attributes:
        execution_reach: How many execution paths / behaviors are affected.
        fan_out: Number of downstream consumers (callers, dependents, subscribers).
        propagation_depth: How far execution travels from entry to terminal.
        boundary_crossings: Number of architectural boundaries crossed.
        sharedness: Number of incoming references / dependents / consumers.
        external_surface: Number of external endpoints affected.
        data_surface: Number of data entities / tables / collections affected.
        validation_gap: Ratio (0.0-1.0) of uncovered execution paths.
        evidence_density: Number of independent evidence objects.
        cross_domain_evidence: Number of evidence sources from different compiler stages.
    """
    execution_reach: int = 0
    fan_out: int = 0
    propagation_depth: int = 0
    boundary_crossings: int = 0
    sharedness: int = 0
    external_surface: int = 0
    data_surface: int = 0
    validation_gap: float = 0.0
    evidence_density: int = 0
    cross_domain_evidence: int = 0


# =========================================================================
# Ranking Vector (lexicographic ORDER BY, not a score)
# =========================================================================

@dataclass(frozen=True, order=True)
class RankingVector:
    """Lexicographic ranking vector for ORDER BY sorting.

    Each component is a comparable value. Sorting is lexicographic —
    exactly like SQL ORDER BY.

    Precedence order (highest to lowest):
      1. has_external_surface: 1 if external endpoints exist, else 0
      2. execution_reach: raw count of reachable execution paths
      3. boundary_crossings: raw count of boundaries crossed
      4. propagation_depth: how deep execution travels
      5. sharedness: how many dependents/consumers
      6. validation_gap: 1 if gaps exist, else 0
      7. evidence_density: count of evidence objects

    All values sort descending (higher = more important).
    """
    has_external_surface: int = 0  # 0 or 1
    execution_reach: int = 0
    boundary_crossings: int = 0
    propagation_depth: int = 0
    sharedness: int = 0
    has_validation_gap: int = 0  # 0 or 1
    evidence_density: int = 0

    def __post_init__(self):
        """Clamp has_ fields to 0 or 1."""
        object.__setattr__(self, 'has_external_surface', 1 if self.has_external_surface else 0)
        object.__setattr__(self, 'has_validation_gap', 1 if self.has_validation_gap else 0)


# =========================================================================
# Surprise Vector (ratios, not boolean)
# =========================================================================

@dataclass(frozen=True)
class SurpriseVector:
    """Deterministic surprise measurement for a discovery.

    A surprise is a ratio between observable change size and observed system impact.
    High ratio = high surprise. No AI, no heuristics, no risk labels.

    Attributes:
        reach_ratio: execution_reach / changed_symbols
        propagation_ratio: propagation_depth / changed_files
        boundary_ratio: boundary_crossings / changed_symbols
        fan_out_ratio: fan_out / changed_endpoints
        service_ratio: services_reached / diff_size
        max_ratio: The maximum of all component ratios.
        description: Human-readable description of the dominant surprise.
    """
    reach_ratio: float = 0.0
    propagation_ratio: float = 0.0
    boundary_ratio: float = 0.0
    fan_out_ratio: float = 0.0
    service_ratio: float = 0.0
    max_ratio: float = 0.0
    description: str = ""


# =========================================================================
# Visual Semantic (not renderer-specific)
# =========================================================================

class VisualSemantic(str, Enum):
    """Semantic visual representation kind — NOT renderer-specific formatting.

    The renderer chooses the concrete visual (Markdown, Slack block, React component).
    The compiler chooses the semantic kind.
    """
    METRIC = "metric"
    TIMELINE = "timeline"
    GRAPH = "graph"
    CARD = "card"
    HIERARCHY = "hierarchy"
    TABLE = "table"
    COVERAGE_INDICATOR = "coverage_indicator"


# =========================================================================
# Narrative Position
# =========================================================================

class NarrativePosition(str, Enum):
    """Position in the review narrative.

    Every discovery receives a narrative position. The reviewer's cognitive
    flow is: Context -> Impact -> Details -> Validation -> Evidence.

    This mirrors compiler scheduling — dependency ordering for human cognition.
    """
    SUMMARY = "summary"
    IMPACT = "impact"
    EXECUTION = "execution"
    OPERATIONAL = "operational"
    VALIDATION = "validation"
    EVIDENCE = "evidence"


# =========================================================================
# Presentation Discovery (the core model)
# =========================================================================

@dataclass(frozen=True)
class PresentationDiscovery:
    """A single presentation-level discovery.

    This is the atomic unit the Presentation Compiler operates on.
    Every pass mutates or enriches this model.

    Attributes:
        id: Stable identifier for this discovery.
        kind: The kind of discovery (determines measurement, ranking, visual).
        title: Concise title for the discovery.
        summary: One-line summary of what was found.
        evidence: Traceable evidence backing this discovery.
        metrics: Significance measurements (not scores).
        ranking_vector: Lexicographic ranking vector for ORDER BY.
        surprise: Surprise measurements (vector of ratios).
        visual_semantic: Semantic visual kind (renderer chooses concrete format).
        narrative_position: Position in the review narrative.
        compressed: Whether this discovery is a compressed group.
        children: If compressed, the underlying discovery IDs that were grouped.
        source_artifact: Reference to the source compiler artifact (e.g., "change://...", "behavior://...").
        metadata: Arbitrary metadata preserved from extraction.
    """
    id: str
    kind: DiscoveryKind
    title: str
    summary: str
    evidence: tuple[PresentationEvidence, ...] = field(default_factory=tuple)
    metrics: SignificanceMetrics | None = None
    ranking_vector: RankingVector | None = None
    surprise: SurpriseVector | None = None
    visual_semantic: VisualSemantic | None = None
    narrative_position: NarrativePosition | None = None
    compressed: bool = False
    children: tuple[str, ...] = field(default_factory=tuple)
    source_artifact: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Normalize mutable defaults to immutable types."""
        if isinstance(self.evidence, list):
            object.__setattr__(self, 'evidence', tuple(self.evidence))
        if isinstance(self.children, list):
            object.__setattr__(self, 'children', tuple(self.children))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))


# =========================================================================
# Visual Assignment
# =========================================================================

@dataclass(frozen=True)
class PresentationVisual:
    """Semantic presentation object for a discovery.

    Attributes:
        discovery_id: The discovery this visual represents.
        semantic: The visual semantic kind (metric, timeline, graph, card, hierarchy, table).
        value: The primary value to display.
        label: Human-readable label for this visual.
        details: Additional structured data for rendering.
    """
    discovery_id: str
    semantic: VisualSemantic
    value: str | int | float
    label: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure details is a dict."""
        if isinstance(self.details, dict):
            object.__setattr__(self, 'details', dict(self.details))


# =========================================================================
# Narrative Section
# =========================================================================

@dataclass(frozen=True)
class PresentationNarrative:
    """Ordered narrative section for reviewer consumption.

    Attributes:
        section: The narrative position value (e.g., "summary", "impact", "execution", ...).
        order: Display order (0-based).
        discovery_ids: Ordered discovery IDs in this section.
        description: Brief description of this section.
    """
    section: str
    order: int
    discovery_ids: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""

    def __post_init__(self):
        """Ensure discovery_ids is a tuple."""
        if isinstance(self.discovery_ids, list):
            object.__setattr__(self, 'discovery_ids', tuple(self.discovery_ids))


# =========================================================================
# Summary
# =========================================================================

@dataclass(frozen=True)
class PresentationSummary:
    """Concise summary of the entire presentation.

    Attributes:
        changed_files: Number of changed files.
        changed_symbols: Number of changed symbols.
        affected_behaviors: Number of affected behaviors.
        execution_paths: Total execution paths affected.
        services_reached: Number of services/APIs reached.
        validation_gaps: Number of validation gaps detected.
        surprising_discoveries: Number of surprising discoveries (surprise_vector.max_ratio > threshold).
    """
    changed_files: int = 0
    changed_symbols: int = 0
    affected_behaviors: int = 0
    execution_paths: int = 0
    services_reached: int = 0
    validation_gaps: int = 0
    surprising_discoveries: int = 0


# =========================================================================
# Metadata
# =========================================================================

@dataclass(frozen=True)
class PresentationMetadata:
    """Metadata about the presentation compilation.

    Attributes:
        compiler_version: Version of the presentation compiler.
        compiled_at: ISO timestamp of compilation.
        discovery_count: Total number of discoveries.
        evidence_count: Total number of evidence references.
        pass_count: Number of passes executed.
    """
    compiler_version: str = "2.0.0"
    compiled_at: str = ""
    discovery_count: int = 0
    evidence_count: int = 0
    pass_count: int = 9  # 8 original + Pass 0 Normalization


# =========================================================================
# Normalized Presentation Context (output of Pass 0)
# =========================================================================

@dataclass(frozen=True)
class NormalizedDiscovery:
    """A single normalized discovery entry from any compiler summary.

    Pass 0 (Normalization) converts the four different compiler summaries
    (Change, Behavior, Operational, Discovery) into a single list of these,
    so the rest of the compiler operates over one stable source.
    """
    id: str
    kind: str  # The semantic kind from the source compiler
    title: str
    description: str
    source: str  # "change", "behavior", "operational", "discovery"
    evidence: tuple[PresentationEvidence, ...] = field(default_factory=tuple)
    evidence_ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# =========================================================================
# Presentation IR (the final output)
# =========================================================================

@dataclass(frozen=True)
class PresentationIR:
    """The canonical Presentation IR — stable, platform-independent.

    This is the output of the Presentation Compiler. It is consumed by
    renderers (GitHub, Dashboard, Slack, API, JSON) without modification.

    Renderers never analyze, infer, rank, reorder, compress, or summarize.
    They only translate this IR into the conventions of the target platform.

    Attributes:
        metadata: Metadata about this presentation.
        summary: Concise summary of discoveries.
        discoveries: All presentation discoveries (enriched through all passes).
        narrative: Ordered narrative sections.
        visuals: Visual semantics for discoveries.
        evidence: All unique supporting evidence references.
        navigation: Navigation hints for reviewers.
    """
    metadata: PresentationMetadata
    summary: PresentationSummary
    discoveries: tuple[PresentationDiscovery, ...] = field(default_factory=tuple)
    narrative: tuple[PresentationNarrative, ...] = field(default_factory=tuple)
    visuals: tuple[PresentationVisual, ...] = field(default_factory=tuple)
    evidence: tuple[PresentationEvidence, ...] = field(default_factory=tuple)
    navigation: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Normalize mutable defaults to immutable types."""
        if isinstance(self.discoveries, list):
            object.__setattr__(self, 'discoveries', tuple(self.discoveries))
        if isinstance(self.narrative, list):
            object.__setattr__(self, 'narrative', tuple(self.narrative))
        if isinstance(self.visuals, list):
            object.__setattr__(self, 'visuals', tuple(self.visuals))
        if isinstance(self.evidence, list):
            object.__setattr__(self, 'evidence', tuple(self.evidence))
        if isinstance(self.navigation, dict):
            object.__setattr__(self, 'navigation', dict(self.navigation))

    # --- Query methods ---

    def get_discovery_by_id(self, discovery_id: str) -> PresentationDiscovery | None:
        """Get a discovery by its identifier."""
        for d in self.discoveries:
            if d.id == discovery_id:
                return d
        return None

    def get_discoveries_by_kind(self, kind: DiscoveryKind) -> tuple[PresentationDiscovery, ...]:
        """Get all discoveries of a specific kind."""
        return tuple(d for d in self.discoveries if d.kind == kind)

    def get_discoveries_by_narrative_position(
        self, position: NarrativePosition
    ) -> tuple[PresentationDiscovery, ...]:
        """Get all discoveries at a narrative position."""
        return tuple(d for d in self.discoveries if d.narrative_position == position)

    def get_surprising_discoveries(self, threshold: float = 5.0) -> tuple[PresentationDiscovery, ...]:
        """Get all discoveries with max surprise ratio above threshold."""
        return tuple(
            d for d in self.discoveries
            if d.surprise is not None and d.surprise.max_ratio >= threshold
        )

    def get_narrative_section(self, section: str) -> PresentationNarrative | None:
        """Get a narrative section by name."""
        for n in self.narrative:
            if n.section == section:
                return n
        return None

    def get_visuals_for_discovery(self, discovery_id: str) -> tuple[PresentationVisual, ...]:
        """Get all visuals for a specific discovery."""
        return tuple(v for v in self.visuals if v.discovery_id == discovery_id)