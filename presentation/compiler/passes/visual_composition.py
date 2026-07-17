"""Pass 7 — Visual Composition.

Responsibility:
    Assign a VisualSemantic to each discovery.
    Not colors, not HTML — semantic kinds the renderer maps to concrete visuals.

Input Contract:
    context.discoveries: list[PresentationDiscovery] (narrative positions assigned)

Output Contract:
    context.visuals: list[PresentationVisual]
        Every discovery gets a VisualSemantic. Visuals reference discovery IDs.

Transformation:
    Map discovery kind -> VisualSemantic:
        ADDED_SYMBOLS, REMOVED_SYMBOLS, MODIFIED_SYMBOLS, CHANGED_ENDPOINTS
            -> VisualSemantic.METRIC
        EXECUTION_CHAIN, BEHAVIOR, ENTRY_POINT, TERMINAL_POINT
            -> VisualSemantic.TIMELINE
        SHARED_EXECUTION, DEPENDENCY_SURFACE
            -> VisualSemantic.GRAPH
        EXECUTION_SURFACE, REACHABLE_UNITS, EXECUTION_DEPTH
            -> VisualSemantic.CARD
        API_SURFACE, DATA_SURFACE, EVENT_SURFACE, CHANGED_IMPORTS
            -> VisualSemantic.TABLE
        VALIDATION_COVERAGE, VALIDATION_GAP
            -> VisualSemantic.COVERAGE_INDICATOR
        COMPRESSED
            -> VisualSemantic.HIERARCHY

Algorithm:
    for discovery in discoveries:
        semantic = kind_semantic_map.get(discovery.kind, VisualSemantic.METRIC)
        visual = PresentationVisual(
            discovery_id=discovery.id,
            semantic=semantic,
            value=extract_value(discovery),
            label=discovery.title,
            details=discovery.metadata,
        )
        visuals.append(visual)
        context.update_discovery(discovery.id, visual_semantic=semantic)

Invariants:
    - Every discovery receives exactly one VisualSemantic.
    - Visuals are semantic — renderer chooses concrete visual (Markdown, Slack, React).
    - No renderer-specific formatting exists here.

Failure Conditions:
    - If discovery kind is unknown, default to VisualSemantic.METRIC.
    - If no discoveries exist, return empty list.

Complexity:
    O(N) where N = number of discoveries.

Must Never:
    - Choose colors, fonts, spacing, or layout.
    - Generate HTML, Markdown, Slack blocks, or any renderer-specific output.
    - Access renderer-specific formats.
"""
from __future__ import annotations

from typing import cast

from presentation.model import (
    PresentationDiscovery,
    PresentationVisual,
    DiscoveryKind,
    VisualSemantic,
)
from .base import PresentationPassContext, PresentationCompilationPass


# Map discovery kind -> visual semantic
KIND_SEMANTIC_MAP: dict[DiscoveryKind, VisualSemantic] = {
    DiscoveryKind.ADDED_SYMBOLS: VisualSemantic.METRIC,
    DiscoveryKind.REMOVED_SYMBOLS: VisualSemantic.METRIC,
    DiscoveryKind.MODIFIED_SYMBOLS: VisualSemantic.METRIC,
    DiscoveryKind.CHANGED_ENDPOINTS: VisualSemantic.METRIC,
    DiscoveryKind.CHANGED_IMPORTS: VisualSemantic.TABLE,
    DiscoveryKind.EXECUTION_SURFACE: VisualSemantic.CARD,
    DiscoveryKind.EXECUTION_CHAIN: VisualSemantic.TIMELINE,
    DiscoveryKind.REACHABLE_UNITS: VisualSemantic.CARD,
    DiscoveryKind.EXECUTION_DEPTH: VisualSemantic.CARD,
    DiscoveryKind.BEHAVIOR: VisualSemantic.TIMELINE,
    DiscoveryKind.ENTRY_POINT: VisualSemantic.TIMELINE,
    DiscoveryKind.TERMINAL_POINT: VisualSemantic.TIMELINE,
    DiscoveryKind.SHARED_EXECUTION: VisualSemantic.GRAPH,
    DiscoveryKind.API_SURFACE: VisualSemantic.TABLE,
    DiscoveryKind.DATA_SURFACE: VisualSemantic.TABLE,
    DiscoveryKind.EVENT_SURFACE: VisualSemantic.TABLE,
    DiscoveryKind.DEPENDENCY_SURFACE: VisualSemantic.GRAPH,
    DiscoveryKind.VALIDATION_COVERAGE: VisualSemantic.COVERAGE_INDICATOR,
    DiscoveryKind.VALIDATION_GAP: VisualSemantic.COVERAGE_INDICATOR,
    DiscoveryKind.COMPRESSED: VisualSemantic.HIERARCHY,
}


class VisualCompositionPass(PresentationCompilationPass):
    """
    Pass 7: Assigns semantic visual kinds to discoveries.

    The renderer (GitHub, Slack, Dashboard) chooses the concrete visual.
    The compiler chooses only the semantic kind.
    """

    @property
    def name(self) -> str:
        return "visual_composition"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Assign visual semantics to all discoveries."""
        if not context.discoveries:
            return context

        visuals: list[PresentationVisual] = []

        for discovery in context.discoveries:
            visual = self._create_visual(discovery)
            visuals.append(visual)
            context.update_discovery(discovery.id, visual_semantic=visual.semantic)

        context.visuals = visuals
        return context

    def _create_visual(self, discovery: PresentationDiscovery) -> PresentationVisual:
        """Create a visual assignment for a single discovery."""
        semantic = KIND_SEMANTIC_MAP.get(discovery.kind, VisualSemantic.METRIC)
        value = self._extract_value(discovery)

        return PresentationVisual(
            discovery_id=discovery.id,
            semantic=semantic,
            value=value,
            label=discovery.title,
            details={
                "kind": discovery.kind.value,
                "evidence_count": len(discovery.evidence),
                "narrative_position": discovery.narrative_position.value if discovery.narrative_position else "",
                **discovery.metadata,
            },
        )

    def _extract_value(self, discovery: PresentationDiscovery) -> str | int | float:
        """Extract a display value from a discovery."""
        # For compressed discoveries, use the count
        if discovery.compressed:
            compressed_count = discovery.metadata.get("compressed_count")
            if compressed_count is not None:
                return cast(int, compressed_count)
            return len(discovery.children)

        # For metric-type discoveries, use evidence count
        semantic = KIND_SEMANTIC_MAP.get(discovery.kind, VisualSemantic.METRIC)

        if semantic in (VisualSemantic.METRIC, VisualSemantic.CARD, VisualSemantic.COVERAGE_INDICATOR):
            return len(discovery.evidence)

        if semantic == VisualSemantic.TABLE:
            return len(discovery.evidence)

        # For timeline, graph, hierarchy, use title as display value
        return discovery.title