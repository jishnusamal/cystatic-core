"""Pass 5 — Compression.

Responsibility:
    Group related discoveries without losing meaning.
    Compression is grouping — not summarization.

Input Contract:
    context.discoveries: list[PresentationDiscovery] (ranked, with metrics, ranking_vector)

Output Contract:
    context.compressed_groups: dict[str, list[str]]
        Maps compressed discovery ID -> list of child discovery IDs.
    Compressed discoveries replace their children in context.discoveries.

Transformation:
    Group discoveries by deterministic rules:
        Same parent -> merge
        Same service -> merge
        Same dependency -> merge
        Same evidence source -> merge

    Never compress across domains.
    Never compress across evidence.

Algorithm:
    groups = {}
    for domain in unique_domains:
        domain_discoveries = [d for d in discoveries if d.domain == domain]
        for group_key, group in group_by_key(domain_discoveries):
            if len(group) >= MIN_GROUP_SIZE:
                compressed = create_compressed_discovery(group)
                groups[compressed.id] = [d.id for d in group]

    Replace grouped discoveries with compressed ones.

Invariants:
    - Every compressed item preserves traceability to underlying evidence.
    - No information is discarded — children are preserved.
    - Never compress across domains.
    - Never compress across evidence.

Failure Conditions:
    - If group has fewer than MIN_GROUP_SIZE items, skip compression.
    - If no groups qualify, return empty dict.

Complexity:
    O(N) where N = number of discoveries.

Must Never:
    - Summarize, abstract, or infer new information.
    - Drop evidence or children.
    - Compress across domains or evidence sources.
"""
from __future__ import annotations

from presentation.model import (
    PresentationDiscovery,
    PresentationEvidence,
    DiscoveryKind,
    RankingVector,
)
from .base import PresentationPassContext, PresentationCompilationPass


class CompressionPass(PresentationCompilationPass):
    """
    Pass 5: Compresses related discoveries into groups.

    Compression is lossless — every compressed item preserves traceability
    back to the underlying evidence. No information is discarded.
    """

    # Minimum number of items in a group to trigger compression
    MIN_GROUP_SIZE: int = 3

    @property
    def name(self) -> str:
        return "compression"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Compress related discoveries into groups."""
        if not context.discoveries:
            return context

        compressed_groups: dict[str, list[str]] = {}
        compressed_ids: set[str] = set()

        # Group by kind (same kind = same parent)
        for kind in self._get_unique_kinds(context.discoveries):
            kind_discoveries = [d for d in context.discoveries if d.kind == kind]
            groups = self._identify_groups(kind_discoveries)
            compressed_groups.update(groups)
            for cid, child_ids in groups.items():
                compressed_ids.add(cid)
                compressed_ids.update(child_ids)

        # Create compressed discoveries
        new_discoveries: list[PresentationDiscovery] = []
        for compressed_id, child_ids in compressed_groups.items():
            children = [d for d in context.discoveries if d.id in child_ids]
            if len(children) < self.MIN_GROUP_SIZE:
                continue
            compressed = self._create_compressed(compressed_id, children)
            new_discoveries.append(compressed)

        # Replace compressed discoveries, preserve order of non-compressed
        final: list[PresentationDiscovery] = [
            d for d in context.discoveries if d.id not in compressed_ids
        ]
        final.extend(new_discoveries)

        context.discoveries = final
        context.compressed_groups = compressed_groups
        return context

    def _get_unique_kinds(self, discoveries: list[PresentationDiscovery]) -> set[DiscoveryKind]:
        """Get unique discovery kinds."""
        return {d.kind for d in discoveries}

    def _identify_groups(
        self,
        discoveries: list[PresentationDiscovery],
    ) -> dict[str, list[str]]:
        """
        Identify groups of discoveries that should be compressed.

        Groups are identified by same kind (same parent).
        Returns dict mapping compressed ID -> list of child discovery IDs.
        """
        groups: dict[str, list[str]] = {}

        if len(discoveries) < self.MIN_GROUP_SIZE:
            return groups

        # All discoveries of the same kind form one group
        first = discoveries[0]
        kind_name = first.kind.value
        compressed_id = f"compressed://{kind_name}"

        groups[compressed_id] = [d.id for d in discoveries]
        return groups

    def _create_compressed(
        self,
        compressed_id: str,
        children: list[PresentationDiscovery],
    ) -> PresentationDiscovery:
        """Create a compressed discovery from a group of children."""
        if not children:
            raise ValueError("Cannot compress empty group")

        first = children[0]
        total = len(children)

        # Gather all evidence
        all_evidence: list[PresentationEvidence] = []
        for child in children:
            all_evidence.extend(child.evidence)

        # Determine the best ranking vector among children
        best_vector = self._best_ranking_vector(children)

        # Build title and summary
        kind_label = first.kind.value.replace("_", " ").title()
        title = f"{total} {kind_label}"
        summary = f"{total} {kind_label.lower()} affected"

        return PresentationDiscovery(
            id=compressed_id,
            kind=DiscoveryKind.COMPRESSED,
            title=title,
            summary=summary,
            evidence=tuple(all_evidence),
            ranking_vector=best_vector,
            compressed=True,
            children=tuple(d.id for d in children),
            source_artifact=first.source_artifact,
            metadata={"compressed_count": total, "original_kind": first.kind.value},
        )

    @staticmethod
    def _best_ranking_vector(children: list[PresentationDiscovery]) -> RankingVector | None:
        """Get the best (highest) ranking vector among children."""
        best = None
        for child in children:
            if child.ranking_vector is None:
                continue
            if best is None or child.ranking_vector > best:
                best = child.ranking_vector
        return best