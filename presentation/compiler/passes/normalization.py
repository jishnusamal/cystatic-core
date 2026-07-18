"""Pass 0 — Normalization.

Responsibility:
    Convert DiscoveryIR into a presentation-ready format.
    The Discovery Compiler has already performed all deterministic analysis.
    This pass simply adapts Discovery objects for presentation.

Input Contract:
    context.discovery_ir: DiscoveryIR
        Contains fully-formed Discovery objects with statements, evidence, and support.

Output Contract:
    context.normalized_discoveries: list[Discovery]
        Every Discovery from DiscoveryIR becomes available for extraction.

Transformation:
    For each Discovery in DiscoveryIR:
        1. Preserve the complete natural-language statement
        2. Preserve all evidence
        3. Preserve all support measurements
        4. Preserve metadata

Algorithm:
    normalized = list(discovery_ir.discoveries)
    context.normalized_discoveries = normalized

Invariants:
    - Every Discovery becomes available for extraction.
    - Never lose evidence — evidence is preserved verbatim.
    - Never modify discovery statements.
    - No ranking, no filtering, no sorting.

Failure Conditions:
    - If discovery_ir is None -> return empty list (no error).

Complexity:
    O(N) where N = number of discoveries.

Must Never:
    - Analyze, rank, filter, sort, merge, compress, or summarize.
    - Interpret or infer new facts.
    - Access renderer-specific formats.
"""
from __future__ import annotations

from typing import Any

from operational.discovery.model import Discovery
from presentation.model import (
    PresentationEvidence,
    NormalizedDiscovery,
)
from .base import PresentationPassContext, PresentationCompilationPass


class NormalizationPass(PresentationCompilationPass):
    """
    Pass 0: Normalizes four compiler summaries into a single canonical source.

    This pass exists so every pass after it operates over one stable model,
    not four unrelated compiler artifacts.
    """

    @property
    def name(self) -> str:
        return "normalization"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Normalize DiscoveryIR into presentation-ready format."""
        discovery_ir = context.discovery_ir
        if discovery_ir is None:
            return context

        # Simply pass through all discoveries from DiscoveryIR
        # The Discovery Compiler has already done all the analysis
        context.normalized_discoveries = list(discovery_ir.discoveries)
        return context

    def _normalize_change_summary(
        self,
        model: Any,
        next_id: Any,
    ) -> list[NormalizedDiscovery]:
        """DEPRECATED: Change normalization moved to Discovery Compiler."""
        return []

    def _normalize_behavior_summary(
        self,
        model: Any,
        next_id: Any,
    ) -> list[NormalizedDiscovery]:
        """DEPRECATED: Behavior normalization moved to Discovery Compiler."""
        return []

    def _normalize_execution_summary(
        self,
        model: Any,
        next_id: Any,
    ) -> list[NormalizedDiscovery]:
        """DEPRECATED: Execution normalization moved to Discovery Compiler."""
        return []

    def _normalize_operational_summary(
        self,
        model: Any,
        next_id: Any,
    ) -> list[NormalizedDiscovery]:
        """DEPRECATED: Operational normalization moved to Discovery Compiler."""
        return []

    @staticmethod
    def _count_attribute(obj: object, attr_names: tuple[str, ...]) -> int:
        """Count items from the first matching attribute name."""
        for name in attr_names:
            if hasattr(obj, name):
                items = getattr(obj, name)
                if isinstance(items, (list, tuple, set, frozenset)):
                    return len(items)
                if hasattr(items, '__len__'):
                    return len(items)
                return 1
        return 0
