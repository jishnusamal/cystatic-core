"""
Evidence Normalizer — orchestrates the normalization process.

This module coordinates all normalization stages to transform
InferenceResult into NormalizedReviewFacts.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.normalized_facts import NormalizedReviewFacts
from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.pipelines.inference import InferenceResult

from .architectural_fact_builder import ArchitecturalFactBuilder
from .risk_canonicalizer import RiskCanonicalizer
from .invariant_builder import InvariantBuilder
from .validation_gap_builder import ValidationGapBuilder
from .reviewer_question_builder import ReviewerQuestionBuilder
from .merge_fact_builder import MergeFactBuilder


class EvidenceNormalizer:
    """Orchestrates the evidence normalization process.
    
    This normalizer transforms InferenceResult into NormalizedReviewFacts
    through multiple stages:
      1. Extract architectural facts
      2. Canonicalize risks
      3. Build production invariants
      4. Identify validation gaps
      5. Generate reviewer questions
      6. Build merge facts
    """
    
    @staticmethod
    def normalize(
        inference_result: InferenceResult,
        bundle: EvidenceBundle,
    ) -> NormalizedReviewFacts:
        """Normalize inference results into reviewer-ready facts.
        
        Args:
            inference_result: Result from InferencePipeline.
            bundle: EvidenceBundle from EvidencePipeline.
            
        Returns:
            NormalizedReviewFacts ready for ReviewPipeline.
        """
        print("Normalizing evidence into reviewer-ready facts...")
        
        # Stage 1: Extract architectural facts
        print("  Stage 1: Extracting architectural facts...")
        architectural_facts = ArchitecturalFactBuilder.build(
            bundle=bundle,
            hypotheses=inference_result.hypotheses,
            evidence_clusters=inference_result.evidence_clusters,
        )
        
        # Stage 2: Canonicalize risks
        print("  Stage 2: Canonicalizing risks...")
        canonical_risks = RiskCanonicalizer.canonicalize(
            bundle=bundle,
            hypotheses=inference_result.hypotheses,
        )
        
        # Stage 3: Build production invariants
        print("  Stage 3: Building production invariants...")
        production_invariants = InvariantBuilder.build(
            bundle=bundle,
            hypotheses=inference_result.hypotheses,
        )
        
        # Stage 4: Identify validation gaps
        print("  Stage 4: Identifying validation gaps...")
        validation_gaps = ValidationGapBuilder.build(
            bundle=bundle,
            invariants=production_invariants,
        )
        
        # Stage 5: Generate reviewer questions
        print("  Stage 5: Generating reviewer questions...")
        reviewer_questions = ReviewerQuestionBuilder.build(
            bundle=bundle,
            validation_gaps=validation_gaps,
            scenarios=inference_result.scenarios,
        )
        
        # Stage 6: Build merge facts
        print("  Stage 6: Building merge facts...")
        merge_facts = MergeFactBuilder.build(
            bundle=bundle,
            validation_gaps=validation_gaps,
            canonical_risks=canonical_risks,
            scenarios=inference_result.scenarios,
        )
        
        # Build verdict input
        verdict_input = EvidenceNormalizer._build_verdict_input(
            canonical_risks=canonical_risks,
            validation_gaps=validation_gaps,
            scenarios=inference_result.scenarios,
        )
        
        # Calculate overall confidence
        overall_confidence = EvidenceNormalizer._calculate_overall_confidence(
            architectural_facts=architectural_facts,
            canonical_risks=canonical_risks,
            production_invariants=production_invariants,
        )
        
        print(f"Normalization complete: {len(architectural_facts)} facts, "
              f"{len(canonical_risks)} risks, {len(production_invariants)} invariants, "
              f"{len(validation_gaps)} gaps, {len(reviewer_questions)} questions, "
              f"{len(merge_facts)} merge facts")
        
        return NormalizedReviewFacts(
            verdict_input=verdict_input,
            architectural_facts=architectural_facts,
            canonical_risks=canonical_risks,
            production_invariants=production_invariants,
            validation_gaps=validation_gaps,
            reviewer_questions=reviewer_questions,
            merge_facts=merge_facts,
            compression_stats=inference_result.compression.to_dict() if inference_result.compression else {},
            overall_confidence=overall_confidence,
        )
    
    @staticmethod
    def _build_verdict_input(
        canonical_risks: list[Any],
        validation_gaps: list[Any],
        scenarios: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build input for verdict determination."""
        # Count high-confidence risks
        high_conf_risks = [r for r in canonical_risks if r.confidence >= 0.8]
        
        # Count critical validation gaps
        critical_gaps = [g for g in validation_gaps if g.confidence >= 0.8]
        
        # Count uncovered scenarios
        uncovered_scenarios = [s for s in scenarios if not s.get("ci_would_catch", False)]
        
        # Determine deterministic status
        if high_conf_risks or critical_gaps:
            status = "REVIEW_REQUIRED"
        elif uncovered_scenarios:
            status = "REVIEW_REQUIRED"
        else:
            status = "APPROVE"
        
        return {
            "status": status,
            "high_confidence_risks": len(high_conf_risks),
            "critical_validation_gaps": len(critical_gaps),
            "uncovered_scenarios": len(uncovered_scenarios),
            "total_risks": len(canonical_risks),
            "total_gaps": len(validation_gaps),
        }
    
    @staticmethod
    def _calculate_overall_confidence(
        architectural_facts: list[Any],
        canonical_risks: list[Any],
        production_invariants: list[Any],
    ) -> float:
        """Calculate overall confidence in the analysis."""
        confidences = []
        
        # Collect confidences from all sources
        for fact in architectural_facts:
            confidences.append(fact.confidence)
        
        for risk in canonical_risks:
            confidences.append(risk.confidence)
        
        for invariant in production_invariants:
            confidences.append(invariant.confidence)
        
        # Calculate average confidence
        if confidences:
            return round(sum(confidences) / len(confidences), 2)
        
        return 1.0