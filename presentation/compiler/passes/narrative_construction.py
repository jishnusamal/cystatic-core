"""Pass 6 — Narrative Construction.

Responsibility:
    Assign a narrative position to every discovery.
    This is dependency ordering — not storytelling.

    The reviewer's brain wants: Context -> Impact -> Details -> Validation -> Evidence.

Input Contract:
    context.discoveries: list[PresentationDiscovery] (ranked, with metrics, ranking_vector)

Output Contract:
    context.narrative_sections: list[PresentationNarrative]
        Ordered sections containing discovery IDs in display order.
    Every discovery has its narrative_position populated.

Transformation:
    Map discovery kind -> narrative position:
        ADDED_SYMBOLS, REMOVED_SYMBOLS, MODIFIED_SYMBOLS, CHANGED_ENDPOINTS, CHANGED_IMPORTS
            -> NarrativePosition.IMPACT
        EXECUTION_SURFACE, EXECUTION_CHAIN, REACHABLE_UNITS, EXECUTION_DEPTH, BEHAVIOR,
          ENTRY_POINT, TERMINAL_POINT, SHARED_EXECUTION
            -> NarrativePosition.EXECUTION
        API_SURFACE, DATA_SURFACE, EVENT_SURFACE, DEPENDENCY_SURFACE
            -> NarrativePosition.OPERATIONAL
        VALIDATION_COVERAGE, VALIDATION_GAP
            -> NarrativePosition.VALIDATION
        COMPRESSED
            -> derived from children or default to EVIDENCE

    Within each section, discoveries are ordered by their ranking vector (descending).

Algorithm:
    position_map = {
        kind -> NarrativePosition
        ...
    }

    for section in [SUMMARY, IMPACT, EXECUTION, OPERATIONAL, VALIDATION, EVIDENCE]:
        discoveries = [d for d in all_discoveries
                       if position_map.get(d.kind) == section]
        discoveries.sort(key=lambda d: d.ranking_vector, reverse=True)
        ids = [d.id for d in discoveries]
        narrative_sections.append(PresentationNarrative(
            section=section.value,
            order=order++,
            discovery_ids=ids,
            description=section_description,
        ))

    for d in discoveries:
        d.narrative_position = position_map.get(d.kind, NarrativePosition.EVIDENCE)

Invariants:
    - Every discovery receives exactly one narrative position.
    - Every PR has the identical structural sections.
    - Within sections, order is deterministic (by ranking vector).

Failure Conditions:
    - If a discovery kind is unknown, default to EVIDENCE.
    - If no discoveries for a section, the section still exists (empty).

Complexity:
    O(N log N) where N = number of discoveries.

Must Never:
    - Write prose, sentences, or storytelling.
    - Reorder sections or change the structural template.
    - Access renderer-specific formats.
"""
from __future__ import annotations

from presentation.model import (
    PresentationDiscovery,
    PresentationNarrative,
    DiscoveryKind,
    NarrativePosition,
    RankingVector,
)
from .base import PresentationPassContext, PresentationCompilationPass


# Map discovery kind -> narrative position
KIND_POSITION_MAP: dict[DiscoveryKind, NarrativePosition] = {
    # Impact: what changed
    DiscoveryKind.ADDED_SYMBOLS: NarrativePosition.IMPACT,
    DiscoveryKind.REMOVED_SYMBOLS: NarrativePosition.IMPACT,
    DiscoveryKind.MODIFIED_SYMBOLS: NarrativePosition.IMPACT,
    DiscoveryKind.CHANGED_ENDPOINTS: NarrativePosition.IMPACT,
    DiscoveryKind.CHANGED_IMPORTS: NarrativePosition.IMPACT,
    # Execution: how execution changes
    DiscoveryKind.EXECUTION_SURFACE: NarrativePosition.EXECUTION,
    DiscoveryKind.EXECUTION_CHAIN: NarrativePosition.EXECUTION,
    DiscoveryKind.REACHABLE_UNITS: NarrativePosition.EXECUTION,
    DiscoveryKind.EXECUTION_DEPTH: NarrativePosition.EXECUTION,
    DiscoveryKind.BEHAVIOR: NarrativePosition.EXECUTION,
    DiscoveryKind.ENTRY_POINT: NarrativePosition.EXECUTION,
    DiscoveryKind.TERMINAL_POINT: NarrativePosition.EXECUTION,
    DiscoveryKind.SHARED_EXECUTION: NarrativePosition.EXECUTION,
    # Operational: system impact
    DiscoveryKind.API_SURFACE: NarrativePosition.OPERATIONAL,
    DiscoveryKind.DATA_SURFACE: NarrativePosition.OPERATIONAL,
    DiscoveryKind.EVENT_SURFACE: NarrativePosition.OPERATIONAL,
    DiscoveryKind.DEPENDENCY_SURFACE: NarrativePosition.OPERATIONAL,
    # Validation: test coverage
    DiscoveryKind.VALIDATION_COVERAGE: NarrativePosition.VALIDATION,
    DiscoveryKind.VALIDATION_GAP: NarrativePosition.VALIDATION,
    # Compressed: derive from children or default
    DiscoveryKind.COMPRESSED: NarrativePosition.EVIDENCE,
}

# Fixed narrative structure
NARRATIVE_STRUCTURE: list[tuple[NarrativePosition, str]] = [
    (NarrativePosition.IMPACT, "What symbols, files, and endpoints changed"),
    (NarrativePosition.EXECUTION, "How execution paths, chains, and behaviors are affected"),
    (NarrativePosition.OPERATIONAL, "Operational effects including APIs, data, events, and dependencies"),
    (NarrativePosition.VALIDATION, "Test coverage and validation gaps for affected paths"),
    (NarrativePosition.EVIDENCE, "Supporting evidence and traceable facts"),
]

# Description for each section
SECTION_DESCRIPTIONS: dict[NarrativePosition, str] = {
    NarrativePosition.IMPACT: "What changed in the codebase",
    NarrativePosition.EXECUTION: "How execution is affected",
    NarrativePosition.OPERATIONAL: "Operational impact of the change",
    NarrativePosition.VALIDATION: "Validation and test coverage",
    NarrativePosition.EVIDENCE: "Supporting evidence",
}


class NarrativeConstructionPass(PresentationCompilationPass):
    """
    Pass 6: Assigns narrative positions to discoveries and builds ordered sections.

    This is dependency ordering for the reviewer's brain — not storytelling.
    Every PR has the identical structural sections.
    """

    @property
    def name(self) -> str:
        return "narrative_construction"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Assign narrative positions and build ordered sections."""
        if not context.discoveries:
            return context

        # Assign narrative positions
        for discovery in context.discoveries:
            position = self._assign_position(discovery, context)
            context.update_discovery(discovery.id, narrative_position=position)

        # Build ordered narrative sections
        narrative_sections: list[PresentationNarrative] = []

        for order, (position, description) in enumerate(NARRATIVE_STRUCTURE):
            ids = self._get_discovery_ids_for_position(position, context)
            narrative_sections.append(PresentationNarrative(
                section=position.value,
                order=order,
                discovery_ids=tuple(ids),
                description=description,
            ))

        # Add summary section at the beginning (always first)
        summary_ids = self._get_summary_ids(context)
        narrative_sections.insert(0, PresentationNarrative(
            section=NarrativePosition.SUMMARY.value,
            order=0,
            discovery_ids=tuple(summary_ids),
            description="High-level overview of the change and its impact",
        ))

        # Re-index orders
        for i, ns in enumerate(narrative_sections):
            narrative_sections[i] = PresentationNarrative(
                section=ns.section,
                order=i,
                discovery_ids=ns.discovery_ids,
                description=ns.description,
            )

        context.narrative_sections = narrative_sections
        return context

    def _assign_position(
        self,
        discovery: PresentationDiscovery,
        context: PresentationPassContext,
    ) -> NarrativePosition:
        """Assign a narrative position to a discovery."""
        position = KIND_POSITION_MAP.get(discovery.kind)

        if position is not None:
            return position

        # For compressed discoveries, derive position from children
        if discovery.compressed and discovery.children:
            child_positions = set()
            for child_id in discovery.children:
                child = context.get_discovery(child_id)
                if child and child.narrative_position:
                    child_positions.add(child.narrative_position)
            if child_positions:
                # Use the most common position among children
                return max(child_positions, key=lambda p: sum(1 for cp in child_positions if cp == p))
            return NarrativePosition.EVIDENCE

        return NarrativePosition.EVIDENCE

    def _get_discovery_ids_for_position(
        self,
        position: NarrativePosition,
        context: PresentationPassContext,
    ) -> list[str]:
        """Get discovery IDs for a narrative position, ordered by ranking vector."""
        discoveries = [
            d for d in context.discoveries
            if d.narrative_position == position
        ]
        # Sort by ranking vector descending
        discoveries.sort(
            key=lambda d: d.ranking_vector or RankingVector(),
            reverse=True,
        )
        return [d.id for d in discoveries]

    def _get_summary_ids(self, context: PresentationPassContext) -> list[str]:
        """Get discovery IDs for the summary section (top ranked from each category)."""
        summary_ids: list[str] = []

        # Include the top-ranked discovery from each narrative section
        seen_positions: set[NarrativePosition] = set()
        for discovery in context.discoveries:
            pos = discovery.narrative_position
            if pos and pos not in seen_positions and pos != NarrativePosition.SUMMARY:
                seen_positions.add(pos)
                summary_ids.append(discovery.id)

            if len(seen_positions) >= 5:
                break

        return summary_ids