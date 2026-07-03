"""
EvidenceNormalizationPipeline — transforms inference results into reviewer-ready facts.

This pipeline sits between InferencePipeline and ReviewPipeline, converting
internal reasoning artifacts into engineering facts.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.models.normalized_facts import NormalizedReviewFacts
from core_engine.pipelines.inference import InferenceResult


class EvidenceNormalizationPipeline:
    """Transforms InferenceResult into NormalizedReviewFacts.
    
    This pipeline is responsible for:
      - Extracting architectural facts from evidence and hypotheses
      - Canonicalizing risks from related hypotheses
      - Building production invariants
      - Identifying validation gaps
      - Generating reviewer questions
      - Building merge facts
    
    The output is a complete set of reviewer-ready facts that can be
    consumed by the ReviewPipeline without accessing internal artifacts.
    """
    
    @staticmethod
    def run(
        inference_result: InferenceResult,
        bundle: EvidenceBundle,
    ) -> NormalizedReviewFacts:
        """Run the evidence normalization pipeline.
        
        Args:
            inference_result: Result from InferencePipeline.
            bundle: EvidenceBundle from EvidencePipeline.
            
        Returns:
            NormalizedReviewFacts ready for ReviewPipeline.
        """
        from core_engine.normalization.normalizer import EvidenceNormalizer
        
        print("Running evidence normalization pipeline...")
        
        # Normalize inference results into reviewer-ready facts
        normalized_facts = EvidenceNormalizer.normalize(
            inference_result=inference_result,
            bundle=bundle,
        )
        
        print(f"Normalization complete")
        
        return normalized_facts