"""Pass 1 — Discovery Extraction.

Responsibility:
    Convert normalized compiler artifacts into PresentationDiscovery objects.

Input Contract:
    context.normalized_discoveries: list[NormalizedDiscovery]
        Every deterministic fact from all compiler summaries, normalized.

Output Contract:
    context.discoveries: list[PresentationDiscovery]
        Every NormalizedDiscovery becomes exactly one PresentationDiscovery.

Transformation:
    For each NormalizedDiscovery:
        1. Map kind string -> DiscoveryKind enum
        2. Create PresentationDiscovery with:
           - id: stable identifier
           - kind: mapped DiscoveryKind
           - title, summary: from normalized discovery
           - evidence: preserved verbatim
           - source_artifact: preserved
           - metadata: preserved
        3. Append to discoveries list

Algorithm:
    discoveries = []
    for nd in normalized_discoveries:
        kind = map_kind(nd.kind)
        discovery = PresentationDiscovery(
            id=nd.id,
            kind=kind,
            title=nd.title,
            summary=nd.description,
            evidence=nd.evidence,
            source_artifact=nd.source,
            metadata=nd.metadata,
        )
        discoveries.append(discovery)
    return discoveries

Invariants:
    - Every NormalizedDiscovery becomes exactly one PresentationDiscovery.
    - No merging, no filtering, no ranking, no sorting.
    - Evidence is preserved verbatim — never dropped, never modified.

Failure Conditions:
    - If a kind string has no mapping, default to DiscoveryKind.COMPRESSED.
      This ensures forward compatibility with new compiler artifact kinds.

Complexity:
    O(N) where N = number of normalized discoveries.

Must Never:
    - Analyze, rank, filter, sort, merge, compress, or summarize.
    - Interpret or infer new facts from evidence.
    - Drop or modify evidence.
"""
from __future__ import annotations

from presentation.model import (
    DiscoveryKind,
    PresentationDiscovery,
    NormalizedDiscovery,
)
from .base import PresentationPassContext, PresentationCompilationPass


# Kind mapping: normalized kind string -> DiscoveryKind enum
KIND_MAP: dict[str, DiscoveryKind] = {
    "added_symbol": DiscoveryKind.ADDED_SYMBOLS,
    "removed_symbol": DiscoveryKind.REMOVED_SYMBOLS,
    "modified_symbol": DiscoveryKind.MODIFIED_SYMBOLS,
    "changed_endpoint": DiscoveryKind.CHANGED_ENDPOINTS,
    "changed_import": DiscoveryKind.CHANGED_IMPORTS,
    "execution_chain": DiscoveryKind.EXECUTION_CHAIN,
    "reachable_units": DiscoveryKind.REACHABLE_UNITS,
    "execution_depth": DiscoveryKind.EXECUTION_DEPTH,
    "behavior": DiscoveryKind.BEHAVIOR,
    "entry_point": DiscoveryKind.ENTRY_POINT,
    "terminal_point": DiscoveryKind.TERMINAL_POINT,
    "shared_execution": DiscoveryKind.SHARED_EXECUTION,
    "api_surface": DiscoveryKind.API_SURFACE,
    "data_surface": DiscoveryKind.DATA_SURFACE,
    "event_surface": DiscoveryKind.EVENT_SURFACE,
    "dependency_surface": DiscoveryKind.DEPENDENCY_SURFACE,
    "validation_coverage": DiscoveryKind.VALIDATION_COVERAGE,
    "validation_gap": DiscoveryKind.VALIDATION_GAP,
}


class DiscoveryExtractionPass(PresentationCompilationPass):
    """
    Pass 1: Converts normalized discoveries into PresentationDiscovery objects.

    This pass exists to transform the normalized representation into the
    Presentation Discovery model that the rest of the compiler operates on.
    """

    @property
    def name(self) -> str:
        return "discovery_extraction"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Convert every normalized discovery into a presentation discovery."""
        if not context.normalized_discoveries:
            return context

        discoveries: list[PresentationDiscovery] = []

        for nd in context.normalized_discoveries:
            kind = KIND_MAP.get(nd.kind, DiscoveryKind.COMPRESSED)

            discovery = PresentationDiscovery(
                id=nd.id,
                kind=kind,
                title=nd.title,
                summary=nd.description,
                evidence=nd.evidence,
                source_artifact=nd.source,
                metadata=nd.metadata.copy() if nd.metadata else {},
            )
            discoveries.append(discovery)

        context.discoveries = discoveries
        return context