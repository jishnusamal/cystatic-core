"""PresentationContextBuilder — builds GithubCommentContext from PresentationIR.

This is the bridge between the Presentation Compiler and the GitHub comment renderer.
It extracts ALL deterministic facts from the PresentationIR and populates them into
the GithubCommentContext before the LLM is ever called.

The LLM receives only the text fields (executive_summary, review_priority, etc.)
and NEVER sees the deterministic metrics.
"""

from __future__ import annotations

from typing import Any

from presentation.model.presentation_ir import (
    PresentationIR,
    PresentationDiscovery,
    PresentationEvidence,
    NarrativePosition,
)
from presentation.context.comment_context import (
    GithubCommentContext,
    ContextExecutionSection,
    ContextOperationalSection,
    ContextValidationSection,
    ContextSurprisingDiscovery,
)


class PresentationContextBuilder:
    """Builds GithubCommentContext from PresentationIR.
    
    This builder populates every deterministic field before the LLM is called.
    The LLM should never generate, copy, or reconstruct any of these values.
    
    Pipeline:
        PresentationIR → PresentationContextBuilder → GithubCommentContext
                                                          ↓ (merge with LLM narrative)
                                                      GithubComment
                                                          ↓
                                                      Jinja2 Renderer
    """
    
    def build(self, presentation_ir: PresentationIR) -> GithubCommentContext:
        """Build complete GithubCommentContext from PresentationIR.
        
        Args:
            presentation_ir: The compiled PresentationIR from the Presentation Compiler.
            
        Returns:
            Fully populated GithubCommentContext with all compiler-derived facts.
        """
        if presentation_ir is None:
            raise ValueError("presentation_ir is required")
        
        # Extract execution metrics from discoveries
        execution_metrics = self._extract_execution_metrics(presentation_ir)
        
        # Extract operational metrics from discoveries
        operational_metrics = self._extract_operational_metrics(presentation_ir)
        
        # Extract validation metrics
        validation_metrics = self._extract_validation_metrics(presentation_ir)
        
        # Extract evidence
        evidence = self._extract_evidence(presentation_ir)
        
        # Extract surprising discoveries (max_ratio >= 5.0)
        surprising_discoveries = self._extract_surprising_discoveries(presentation_ir)
        
        # Build execution section
        execution_section = ContextExecutionSection(
            execution_paths=execution_metrics["execution_paths"],
            reachable_units=execution_metrics["reachable_units"],
            depth=execution_metrics["depth"],
            highlights=self._extract_execution_highlights(presentation_ir),
        )
        
        # Build operational section
        operational_section = ContextOperationalSection(
            api_count=operational_metrics["api_count"],
            data_count=operational_metrics["data_count"],
            event_count=operational_metrics["event_count"],
            dependency_count=operational_metrics["dependency_count"],
            behavior_count=operational_metrics["behavior_count"],
            symbol_count=operational_metrics["symbol_count"],
        )
        
        # Build validation section
        validation_section = ContextValidationSection(
            gap_count=validation_metrics["gap_count"],
        )
        
        # Build pipeline diagnostics
        pipeline_diagnostics = {
            "compiler_version": presentation_ir.metadata.compiler_version,
            "compiled_at": presentation_ir.metadata.compiled_at,
            "discovery_count": presentation_ir.metadata.discovery_count,
            "evidence_count": presentation_ir.metadata.evidence_count,
        }
        
        return GithubCommentContext(
            execution=execution_section,
            operational=operational_section,
            validation=validation_section,
            surprising_discoveries=surprising_discoveries,
            evidence=evidence,
            pipeline_diagnostics=pipeline_diagnostics,
        )
    
    def _extract_execution_metrics(self, ir: PresentationIR) -> dict[str, int]:
        """Extract execution metrics from PresentationIR.
        
        Sources:
        - Summary: execution_paths
        - Discoveries with execution-related kinds: reachable_units, depth
        """
        execution_paths = ir.summary.execution_paths
        
        # Find reachable_units and depth from discoveries
        reachable_units = 0
        depth = 0
        
        for discovery in ir.discoveries:
            if discovery.kind.value == "reachable_units" and discovery.metrics:
                reachable_units = discovery.metrics.execution_reach
                depth = max(depth, discovery.metrics.propagation_depth)
            
            # Also check execution depth discoveries
            if discovery.kind.value == "execution_depth" and discovery.metrics:
                depth = max(depth, discovery.metrics.propagation_depth)
            
            # Check execution chain discoveries
            if discovery.kind.value == "execution_chain" and discovery.metrics:
                if discovery.metrics.execution_reach > reachable_units:
                    reachable_units = discovery.metrics.execution_reach
                depth = max(depth, discovery.metrics.propagation_depth)
        
        return {
            "execution_paths": execution_paths,
            "reachable_units": reachable_units,
            "depth": depth,
        }
    
    def _extract_operational_metrics(self, ir: PresentationIR) -> dict[str, int]:
        """Extract operational metrics from PresentationIR.
        
        Sources:
        - Discoveries with operational kinds: api_surface, data_surface, event_surface, dependency_surface
        - Summary: services_reached
        """
        api_count = 0
        data_count = 0
        event_count = 0
        dependency_count = 0
        behavior_count = ir.summary.affected_behaviors
        symbol_count = ir.summary.changed_symbols
        
        for discovery in ir.discoveries:
            if not discovery.metrics:
                continue
            
            if discovery.kind.value == "api_surface":
                api_count = discovery.metrics.external_surface
            elif discovery.kind.value == "data_surface":
                data_count = discovery.metrics.data_surface
            elif discovery.kind.value == "event_surface":
                # Events are tracked via fan_out (subscribers/consumers)
                event_count = max(event_count, discovery.metrics.fan_out)
            elif discovery.kind.value == "dependency_surface":
                dependency_count = max(dependency_count, discovery.metrics.sharedness)
        
        # If no specific discoveries found, fall back to summary
        if api_count == 0 and data_count == 0:
            api_count = ir.summary.services_reached
        
        return {
            "api_count": api_count,
            "data_count": data_count,
            "event_count": event_count,
            "dependency_count": dependency_count,
            "behavior_count": behavior_count,
            "symbol_count": symbol_count,
        }
    
    def _extract_validation_metrics(self, ir: PresentationIR) -> dict[str, int]:
        """Extract validation metrics from PresentationIR.
        
        Sources:
        - Summary: validation_gaps
        - Discoveries with validation kinds
        """
        gap_count = ir.summary.validation_gaps
        return {"gap_count": gap_count}
    
    def _extract_evidence(self, ir: PresentationIR) -> tuple[str, ...]:
        """Extract top evidence items from PresentationIR.
        
        Takes the first 10 unique evidence descriptions across all discoveries.
        """
        seen = set()
        evidence_items = []
        
        # Collect evidence from the global evidence list
        for ev in ir.evidence:
            if len(evidence_items) >= 10:
                break
            key = ev.description.lower().strip()
            if key not in seen:
                seen.add(key)
                evidence_items.append(f"{ev.source}: {ev.description}")
        
        # If not enough, collect from discoveries
        if len(evidence_items) < 10:
            for discovery in ir.discoveries:
                if len(evidence_items) >= 10:
                    break
                for ev in discovery.evidence:
                    if len(evidence_items) >= 10:
                        break
                    key = ev.description.lower().strip()
                    if key not in seen:
                        seen.add(key)
                        evidence_items.append(f"{ev.source}: {ev.description}")
        
        return tuple(evidence_items)
    
    def _extract_surprising_discoveries(
        self, ir: PresentationIR
    ) -> tuple[ContextSurprisingDiscovery, ...]:
        """Extract surprising discoveries (max_ratio >= 5.0) from PresentationIR.
        
        Returns top 5 most surprising discoveries.
        """
        surprising = []
        
        for discovery in ir.discoveries:
            if discovery.surprise and discovery.surprise.max_ratio >= 5.0:
                # Build metric string
                metric_parts = []
                if discovery.metrics:
                    if discovery.metrics.execution_reach > 0:
                        metric_parts.append(f"{discovery.metrics.execution_reach} units reached")
                    if discovery.metrics.propagation_depth > 0:
                        metric_parts.append(f"depth {discovery.metrics.propagation_depth}")
                    if discovery.metrics.fan_out > 0:
                        metric_parts.append(f"{discovery.metrics.fan_out} consumers")
                
                # Build support string from top evidence
                support_parts = []
                for ev in discovery.evidence[:2]:  # Max 2 evidence items
                    support_parts.append(ev.description)
                
                surprising.append(ContextSurprisingDiscovery(
                    title=discovery.title,
                    metric=" | ".join(metric_parts) if metric_parts else "",
                    support=" | ".join(support_parts) if support_parts else "",
                ))
        
        # Limit to 5 most surprising
        return tuple(surprising[:5])
    
    def _extract_execution_highlights(
        self, ir: PresentationIR
    ) -> tuple[ContextSurprisingDiscovery, ...]:
        """Extract execution highlights from PresentationIR.
        
        These are notable execution-related findings.
        """
        highlights = []
        
        for discovery in ir.discoveries:
            if not discovery.metrics:
                continue
            
            # Execution-related discoveries with notable metrics
            if discovery.kind.value in ("execution_surface", "execution_chain", "shared_execution"):
                if discovery.surprise and discovery.surprise.max_ratio >= 3.0:
                    metric_parts = []
                    if discovery.metrics.execution_reach > 0:
                        metric_parts.append(f"{discovery.metrics.execution_reach} paths")
                    if discovery.metrics.propagation_depth > 0:
                        metric_parts.append(f"depth {discovery.metrics.propagation_depth}")
                    
                    highlights.append(ContextSurprisingDiscovery(
                        title=discovery.title,
                        metric=" | ".join(metric_parts) if metric_parts else "",
                    ))
        
        return tuple(highlights[:3])  # Max 3 highlights
    
    def build_diagnostic_context(self, ir: PresentationIR) -> GithubCommentContext:
        """Build a context with only diagnostic information (no narrative).
        
        This is used when the LLM pipeline fails entirely.
        The comment will still contain all deterministic compiler facts.
        """
        context = self.build(ir)
        
        # Fill in summary text from compiler evidence
        context = GithubCommentContext(
            executive_summary=f"Analysis completed for {ir.summary.changed_files} changed files, "
                              f"{ir.summary.changed_symbols} symbols, "
                              f"{ir.summary.affected_behaviors} behaviors.",
            review_priority=f"Impact: {ir.summary.execution_paths} execution paths, "
                           f"{ir.summary.services_reached} services",
            biggest_surprise=f"{ir.summary.surprising_discoveries} surprising discoveries found",
            execution_summary=f"{ir.summary.execution_paths} execution paths affecting "
                             f"{ir.summary.affected_behaviors} behaviors",
            operational_summary=f"{ir.summary.services_reached} services affected",
            validation_summary=f"{ir.summary.validation_gaps} validation gaps identified",
            attention="Note: LLM-enhanced comment generation encountered an issue. "
                      "Showing deterministic compiler output.",
            execution=context.execution,
            operational=context.operational,
            validation=context.validation,
            surprising_discoveries=context.surprising_discoveries,
            evidence=context.evidence,
            pipeline_diagnostics={
                **context.pipeline_diagnostics,
                "narrative_source": "compiler_only",
            },
        )
        
        return context