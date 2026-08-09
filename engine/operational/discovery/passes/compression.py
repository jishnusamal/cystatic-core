"""CompressionPass — groups related discoveries without losing meaning.

MOVED FROM: presentation/compiler/passes/compression.py

Responsibility:
    Group related discoveries to reduce noise.
    Compression is grouping — not summarization.

Input Contract:
    context.discoveries: list[Discovery] (ranked, with importance)

Output Contract:
    Related discoveries are grouped into compressed discoveries.
    Compressed discoveries replace their children in the list.
    Children are preserved in metadata for traceability.

Transformation:
    Group discoveries by same kind.
    If group size >= MIN_GROUP_SIZE, create a compressed discovery.

Algorithm:
    groups = {}
    for kind in unique_kinds:
        kind_discoveries = [d for d in discoveries if d.kind == kind]
        if len(kind_discoveries) >= MIN_GROUP_SIZE:
            compressed = create_compressed_discovery(kind_discoveries)
            replace children with compressed

Invariants:
    - Every compressed item preserves traceability to underlying evidence.
    - No information is discarded — children are preserved in metadata.
    - Never compress across kinds.
"""
from __future__ import annotations

from collections import defaultdict

from engine.operational.discovery.model import (
    Discovery,
    DiscoveryKind,
    DiscoverySupport,
    DiscoveryEvidence,
)
from engine.operational.discovery.passes.base import DiscoveryPassContext, DiscoveryCompilerPass


class CompressionPass(DiscoveryCompilerPass):
    """Groups related discoveries without losing meaning.

    Compression is lossless — every compressed item preserves traceability
    back to the underlying evidence. No information is discarded.
    """

    # Minimum number of items in a group to trigger compression
    MIN_GROUP_SIZE: int = 3

    @property
    def name(self) -> str:
        return "compression"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Compress related discoveries into groups."""
        if not context.discoveries:
            return context

        discoveries = context.discoveries

        # Group by kind
        groups: dict[DiscoveryKind, list[Discovery]] = defaultdict(list)
        for d in discoveries:
            groups[d.kind].append(d)

        # Determine which groups should be compressed
        compressed_ids: set[str] = set()
        compressed_replacements: list[Discovery] = []

        for kind, kind_discoveries in groups.items():
            if len(kind_discoveries) < self.MIN_GROUP_SIZE:
                continue
            if kind == DiscoveryKind.COMPRESSED:
                continue  # Don't re-compress

            compressed = self._create_compressed(kind_discoveries)
            compressed_replacements.append(compressed)
            for d in kind_discoveries:
                compressed_ids.add(d.id)

        if not compressed_replacements:
            return context

        # Replace compressed discoveries, preserve order
        final: list[Discovery] = [
            d for d in discoveries if d.id not in compressed_ids
        ]
        final.extend(compressed_replacements)

        context.discoveries = final
        return context

    def _create_compressed(self, discoveries: list[Discovery]) -> Discovery:
        """Create a compressed discovery from a group of same-kind discoveries."""
        if not discoveries:
            raise ValueError("Cannot compress empty group")

        first = discoveries[0]
        kind_label = first.kind.value.replace("_", " ").title()
        total = len(discoveries)

        # Gather all evidence
        all_evidence: list[DiscoveryEvidence] = []
        children: list[str] = []
        total_importance = 0.0
        best_support = first.support

        for d in discoveries:
            all_evidence.extend(d.evidence)
            children.append(d.id)
            total_importance += d.importance
            # Take the best (highest) support values
            s = d.support
            if s.execution_reach > best_support.execution_reach:
                best_support = s

        avg_importance = round(total_importance / total, 2)

        statement = (
            f"{total} {kind_label.lower()} "
            f"{'were' if total != 1 else 'was'} detected."
        )

        return Discovery(
            id=f"compressed://{first.kind.value}",
            kind=DiscoveryKind.COMPRESSED,
            statement=statement,
            importance=avg_importance,
            support=DiscoverySupport(
                execution_reach=best_support.execution_reach,
                fan_in=best_support.fan_in,
                fan_out=best_support.fan_out,
                propagation_depth=best_support.propagation_depth,
                boundary_crossings=best_support.boundary_crossings,
                external_surface=best_support.external_surface,
                data_surface=best_support.data_surface,
                event_surface=best_support.event_surface,
                validation_coverage=best_support.validation_coverage,
                validation_gaps=best_support.validation_gaps,
                shared_by_count=best_support.shared_by_count,
                cross_service_count=best_support.cross_service_count,
                changed_symbol_count=best_support.changed_symbol_count,
                changed_file_count=best_support.changed_file_count,
            ),
            evidence=tuple(all_evidence),
            metadata={
                "compressed_count": total,
                "original_kind": first.kind.value,
                "children": children,
            },
        )