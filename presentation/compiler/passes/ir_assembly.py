"""Pass 8 — Presentation IR Assembly.

Responsibility:
    Assemble all pass outputs into the final PresentationIR.
    Almost no computation — only composition.

Input Contract:
    context.discoveries: list[PresentationDiscovery]
    context.narrative_sections: list[PresentationNarrative]
    context.visuals: list[PresentationVisual]
    context.surprise_map: dict[str, SurpriseVector]
    context.discovery_model: EngineeringDiscoveryModel (for summary counts)

Output Contract:
    context.presentation_ir: PresentationIR
        The canonical, stable, platform-independent output.
        Contains: metadata, summary, discoveries, narrative, visuals, evidence, navigation.

Transformation:
    1. Build summary from discovery counts
    2. Collect all unique evidence from all discoveries
    3. Build navigation (sections, critical discoveries, surprising discoveries)
    4. Build metadata
    5. Assemble PresentationIR

Algorithm:
    summary = PresentationSummary(
        changed_symbols=N,
        affected_behaviors=N,
        execution_paths=N,
        surprising_discoveries=len(surprise_map),
    )

    all_evidence = deduplicated(discovery.evidence for all discoveries)

    navigation = {
        "sections": [...],
        "critical_discoveries": [...],
        "surprising_discoveries": [...],
        "total_discoveries": N,
    }

    metadata = PresentationMetadata(
        compiled_at=now(),
        discovery_count=N,
        evidence_count=len(all_evidence),
    )

    ir = PresentationIR(
        metadata=metadata,
        summary=summary,
        discoveries=discoveries,
        narrative=narrative_sections,
        visuals=visuals,
        evidence=all_evidence,
        navigation=navigation,
    )

Invariants:
    - Every discovery, narrative, visual, and evidence is preserved.
    - No computation — only composition.
    - The IR contains no renderer-specific formatting.

Failure Conditions:
    - If no discoveries exist, produce an empty IR (still valid).
    - If evidence is empty, produce IR with empty evidence tuple (still valid).

Complexity:
    O(N) where N = total discoveries + evidence.

Must Never:
    - Analyze, infer, rank, reorder, compress, or summarize.
    - Generate HTML, Markdown, or any renderer-specific output.
    - Drop or modify discoveries, evidence, or visuals.
"""
from __future__ import annotations

from datetime import datetime, timezone

from presentation.model import (
    PresentationIR,
    PresentationDiscovery,
    PresentationEvidence,
    PresentationSummary,
    PresentationMetadata,
    PresentationNarrative,
    PresentationVisual,
    RankingVector,
)
from .base import PresentationPassContext, PresentationCompilationPass


class IRAssemblyPass(PresentationCompilationPass):
    """
    Pass 8: Assembles all pass outputs into the final PresentationIR.

    This is the terminal pass. It combines all outputs from previous passes
    into a single, stable intermediate representation. Almost no computation —
    only composition.
    """

    COMPILER_VERSION: str = "2.0.0"

    @property
    def name(self) -> str:
        return "ir_assembly"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Assemble the final PresentationIR from all pass outputs."""
        # --- Summary ---
        summary = self._build_summary(context)

        # --- Collect unique evidence ---
        all_evidence = self._collect_evidence(context.discoveries)

        # --- Navigation ---
        navigation = self._build_navigation(context)

        # --- Metadata ---
        metadata = PresentationMetadata(
            compiler_version=self.COMPILER_VERSION,
            compiled_at=datetime.now(timezone.utc).isoformat(),
            discovery_count=len(context.discoveries),
            evidence_count=len(all_evidence),
            pass_count=9,  # 8 + Pass 0 Normalization
        )

        # --- Assemble IR ---
        context.presentation_ir = PresentationIR(
            metadata=metadata,
            summary=summary,
            discoveries=tuple(context.discoveries),
            narrative=tuple(context.narrative_sections),
            visuals=tuple(context.visuals),
            evidence=tuple(all_evidence),
            navigation=navigation,
        )

        return context

    def _build_summary(self, context: PresentationPassContext) -> PresentationSummary:
        """Build summary from discovery counts."""
        model = context.discovery_model

        # Count from discovery model
        changed_symbols = 0
        affected_behaviors = 0
        execution_paths = 0
        services_reached = 0
        validation_gaps = 0

        if model:
            change = getattr(model, 'change', None)
            if change:
                changed_symbols = (
                    len(getattr(change, 'added_symbols', ()))
                    + len(getattr(change, 'removed_symbols', ()))
                    + len(getattr(change, 'modified_symbols', ()))
                )

            behavior = getattr(model, 'behavior', None)
            if behavior:
                affected_behaviors = len(getattr(behavior, 'behaviors', ()))

            chains = getattr(model, 'execution_chains', ())
            execution_paths = len(chains)

            api = getattr(model, 'api', None)
            if api:
                endpoints = getattr(api, 'endpoints', getattr(api, 'routes', ()))
                services_reached = len(endpoints)

            validation = getattr(model, 'validation', None)
            if validation:
                missing = getattr(
                    validation, 'missing_coverage',
                    getattr(validation, 'uncovered',
                            getattr(validation, 'gaps', ()))
                )
                validation_gaps = len(missing)

        return PresentationSummary(
            changed_files=0,  # Not tracked in current model
            changed_symbols=changed_symbols,
            affected_behaviors=affected_behaviors,
            execution_paths=execution_paths,
            services_reached=services_reached,
            validation_gaps=validation_gaps,
            surprising_discoveries=len(context.surprise_map),
        )

    def _collect_evidence(
        self,
        discoveries: list[PresentationDiscovery],
    ) -> list[PresentationEvidence]:
        """Collect all unique evidence from all discoveries."""
        seen: set[str] = set()
        evidence: list[PresentationEvidence] = []

        for discovery in discoveries:
            for ev in discovery.evidence:
                key = f"{ev.source}:{ev.source_id}"
                if key not in seen:
                    seen.add(key)
                    evidence.append(ev)

        return evidence

    def _build_navigation(self, context: PresentationPassContext) -> dict[str, object]:
        """Build navigation hints."""
        navigation: dict[str, object] = {}

        # Sections
        navigation["sections"] = [
            {
                "id": ns.section,
                "order": ns.order,
                "description": ns.description,
                "discovery_count": len(ns.discovery_ids),
            }
            for ns in context.narrative_sections
        ]

        # Top-ranked discoveries (top 3 by ranking vector)
        top_ids = [d.id for d in context.discoveries[:3]]
        navigation["top_discoveries"] = top_ids

        # Surprising discoveries
        navigation["surprising_discoveries"] = list(context.surprise_map.keys())

        # Totals
        navigation["total_discoveries"] = len(context.discoveries)
        navigation["total_visuals"] = len(context.visuals)
        navigation["total_evidence"] = sum(len(d.evidence) for d in context.discoveries)

        return navigation