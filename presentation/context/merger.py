"""Context Merger — merges GithubCommentContext with GithubCommentNarrative.

This is the bridge between deterministic compiler facts and LLM-generated narrative.
The merger produces a single GithubComment that the Jinja2 renderer consumes.

Pipeline:
    GithubCommentContext (deterministic) + GithubCommentNarrative (LLM) → GithubComment → Jinja2
"""

from __future__ import annotations

from presentation.context.comment_context import (
    GithubCommentContext,
    ContextExecutionSection,
    ContextOperationalSection,
    ContextValidationSection,
    ContextSurprisingDiscovery,
)
from presentation.llm.narrative_models import GithubCommentNarrative
from presentation.llm.models import (
    GithubComment,
    ExecutionSection,
    OperationalSection,
    ValidationSection,
    SurprisingDiscovery,
)


class ContextMerger:
    """Merges deterministic context with LLM narrative into a renderable GithubComment.
    
    The merger is responsible for:
    1. Taking all deterministic metrics from GithubCommentContext
    2. Taking all narrative text from GithubCommentNarrative
    3. Producing a single GithubComment that the Jinja2 renderer can consume
    
    If narrative fields are empty (LLM failure), the context's diagnostic
    fallback text is used instead.
    """
    
    def merge(
        self,
        context: GithubCommentContext,
        narrative: GithubCommentNarrative,
    ) -> GithubComment:
        """Merge deterministic context with LLM narrative.
        
        Args:
            context: GithubCommentContext with all compiler-derived facts.
            narrative: GithubCommentNarrative with LLM-generated text.
            
        Returns:
            GithubComment ready for Jinja2 rendering.
        """
        # Merge surprising discoveries: context provides title/metric/support,
        # narrative provides explanation
        merged_discoveries = self._merge_discoveries(
            context.surprising_discoveries,
            narrative.surprising_discoveries,
        )
        
        # Merge evidence: prefer narrative evidence, fall back to context
        merged_evidence = self._merge_evidence(
            context.evidence,
            narrative.evidence,
        )
        
        # Build execution section with context metrics + narrative
        execution_section = ExecutionSection(
            execution_paths=context.execution.execution_paths,
            reachable_units=context.execution.reachable_units,
            depth=context.execution.depth,
            narrative=context.execution.narrative or narrative.execution_summary,
            highlights=tuple(
                SurprisingDiscovery(
                    title=h.title,
                    explanation=h.explanation,
                    metric=h.metric,
                    support=h.support,
                )
                for h in context.execution.highlights
            ),
        )
        
        # Build operational section with context metrics + narrative
        operational_section = OperationalSection(
            api_count=context.operational.api_count,
            data_count=context.operational.data_count,
            event_count=context.operational.event_count,
            dependency_count=context.operational.dependency_count,
            narrative=context.operational.narrative or narrative.operational_summary,
        )
        
        # Build validation section
        validation_section = ValidationSection(
            summary=narrative.validation_summary or context.validation.summary,
        )
        
        # Build the final GithubComment
        comment = GithubComment(
            executive_summary=narrative.executive_summary or context.executive_summary,
            review_priority=narrative.review_priority or context.review_priority,
            biggest_surprise=narrative.biggest_surprise or context.biggest_surprise,
            execution_summary=narrative.execution_summary or context.execution_summary,
            operational_summary=narrative.operational_summary or context.operational_summary,
            validation_summary=narrative.validation_summary or context.validation_summary,
            attention=narrative.attention or context.attention,
            surprising_discoveries=merged_discoveries,
            execution=execution_section,
            operational=operational_section,
            validation=validation_section,
            evidence=merged_evidence,
        )
        
        return comment
    
    def _merge_discoveries(
        self,
        context_discoveries: tuple[ContextSurprisingDiscovery, ...],
        narrative_discoveries: tuple,
    ) -> tuple[SurprisingDiscovery, ...]:
        """Merge context discoveries with narrative explanations.
        
        Each context discovery has title, metric, support (compiler-derived).
        Each narrative discovery has explanation (LLM-generated).
        
        They are matched by position (index).
        """
        merged = []
        
        for i, ctx_disc in enumerate(context_discoveries):
            explanation = ""
            if i < len(narrative_discoveries):
                # Extract explanation from narrative discovery
                narr_disc = narrative_discoveries[i]
                if hasattr(narr_disc, 'explanation'):
                    explanation = narr_disc.explanation
            
            merged.append(SurprisingDiscovery(
                title=ctx_disc.title,
                explanation=explanation,
                metric=ctx_disc.metric,
                support=ctx_disc.support,
            ))
        
        return tuple(merged)
    
    def _merge_evidence(
        self,
        context_evidence: tuple[str, ...],
        narrative_evidence: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Merge evidence items.
        
        Prefer narrative evidence (LLM may rephrase), but fall back to
        context evidence if narrative is empty.
        """
        if narrative_evidence:
            return narrative_evidence
        return context_evidence