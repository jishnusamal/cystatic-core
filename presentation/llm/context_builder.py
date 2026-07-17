"""LLM Context Builder.

Transforms PresentationIR into a compact LLMContext.
Aggressively reduces noise - the LLM never sees raw evidence.
"""

from __future__ import annotations

from typing import Any

from presentation.model import (
    PresentationIR,
    PresentationDiscovery,
    PresentationNarrative,
    PresentationVisual,
    PresentationSummary,
    PresentationMetadata,
)
from presentation.llm.models import (
    LLMContext,
    LLMDiscovery,
    LLMNarrative,
    LLMVisual,
)


class LLMContextBuilder:
    """
    Builds compact LLMContext from PresentationIR.
    
    Responsibilities:
    - Reduce thousands of evidence records to top 5 per discovery
    - Extract only metrics the LLM needs
    - Preserve compiler ranking and ordering
    - Never invent or infer new data
    """
    
    def build(self, presentation_ir: PresentationIR) -> LLMContext:
        """
        Build LLMContext from PresentationIR.
        
        Args:
            presentation_ir: The compiled PresentationIR from the Presentation Compiler.
            
        Returns:
            LLMContext: Compact context ready for LLM consumption.
        """
        if presentation_ir is None:
            raise ValueError("presentation_ir is required")
        
        # Build metadata
        metadata = self._build_metadata(presentation_ir.metadata)
        
        # Build summary
        summary = self._build_summary(presentation_ir.summary)
        
        # Build discoveries (compact, no raw evidence)
        discoveries = self._build_discoveries(presentation_ir.discoveries)
        
        # Build narrative sections
        narrative = self._build_narrative(presentation_ir.narrative)
        
        # Build visuals
        visuals = self._build_visuals(presentation_ir.visuals)
        
        return LLMContext(
            metadata=metadata,
            summary=summary,
            discoveries=discoveries,
            narrative=narrative,
            visuals=visuals,
        )
    
    def _build_metadata(self, metadata: PresentationMetadata | None) -> dict[str, Any]:
        """Build metadata section."""
        if metadata is None:
            return {}
        
        return {
            "compiler_version": metadata.compiler_version,
            "compiled_at": metadata.compiled_at,
            "discovery_count": metadata.discovery_count,
            "evidence_count": metadata.evidence_count,
            "pass_count": metadata.pass_count,
        }
    
    def _build_summary(self, summary: PresentationSummary | None) -> dict[str, Any]:
        """Build summary section with key metrics."""
        if summary is None:
            return {}
        
        return {
            "changed_files": summary.changed_files,
            "changed_symbols": summary.changed_symbols,
            "affected_behaviors": summary.affected_behaviors,
            "execution_paths": summary.execution_paths,
            "services_reached": summary.services_reached,
            "validation_gaps": summary.validation_gaps,
            "surprising_discoveries": summary.surprising_discoveries,
        }
    
    def _build_discoveries(self, discoveries: tuple[PresentationDiscovery, ...]) -> tuple[LLMDiscovery, ...]:
        """
        Build compact discoveries for LLM.
        
        Key principle: No raw evidence lists.
        Instead: Top 5 representative evidence items per discovery.
        """
        llm_discoveries = []
        
        for discovery in discoveries:
            # Extract metrics (already computed by compiler)
            metrics = {}
            if discovery.metrics:
                metrics = {
                    "execution_reach": discovery.metrics.execution_reach,
                    "fan_out": discovery.metrics.fan_out,
                    "propagation_depth": discovery.metrics.propagation_depth,
                    "boundary_crossings": discovery.metrics.boundary_crossings,
                    "sharedness": discovery.metrics.sharedness,
                    "external_surface": discovery.metrics.external_surface,
                    "data_surface": discovery.metrics.data_surface,
                    "validation_gap": discovery.metrics.validation_gap,
                    "evidence_density": discovery.metrics.evidence_density,
                }
            
            # Extract surprise (already computed by compiler)
            surprise = {}
            if discovery.surprise:
                surprise = {
                    "reach_ratio": discovery.surprise.reach_ratio,
                    "propagation_ratio": discovery.surprise.propagation_ratio,
                    "boundary_ratio": discovery.surprise.boundary_ratio,
                    "fan_out_ratio": discovery.surprise.fan_out_ratio,
                    "service_ratio": discovery.surprise.service_ratio,
                    "max_ratio": discovery.surprise.max_ratio,
                    "description": discovery.surprise.description,
                }
            
            # Extract top evidence (max 5 items)
            # The compiler has already ranked discoveries, so we just take the first 5
            top_evidence = []
            for i, evidence in enumerate(discovery.evidence):
                if i >= 5:  # Limit to 5 evidence items
                    break
                # Create concise evidence description
                evidence_str = f"{evidence.source}: {evidence.description}"
                if evidence.evidence_ref:
                    evidence_str += f" ({evidence.evidence_ref})"
                top_evidence.append(evidence_str)
            
            llm_discovery = LLMDiscovery(
                id=discovery.id,
                kind=discovery.kind.value,
                title=discovery.title,
                summary=discovery.summary,
                metrics=metrics,
                surprise=surprise,
                top_evidence=tuple(top_evidence),
                narrative_position=discovery.narrative_position.value if discovery.narrative_position else "",
            )
            llm_discoveries.append(llm_discovery)
        
        return tuple(llm_discoveries)
    
    def _build_narrative(self, narrative: tuple[PresentationNarrative, ...]) -> tuple[LLMNarrative, ...]:
        """Build narrative sections."""
        llm_narrative = []
        
        for section in narrative:
            llm_section = LLMNarrative(
                section=section.section,
                order=section.order,
                description=section.description,
                discovery_ids=section.discovery_ids,
            )
            llm_narrative.append(llm_section)
        
        return tuple(llm_narrative)
    
    def _build_visuals(self, visuals: tuple[PresentationVisual, ...]) -> tuple[LLMVisual, ...]:
        """Build visual semantics."""
        llm_visuals = []
        
        for visual in visuals:
            llm_visual = LLMVisual(
                discovery_id=visual.discovery_id,
                semantic=visual.semantic.value,
                value=visual.value,
                label=visual.label,
            )
            llm_visuals.append(llm_visual)
        
        return tuple(llm_visuals)