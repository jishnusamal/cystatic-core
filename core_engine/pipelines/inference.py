"""
InferencePipeline — generates hypotheses and scenarios from evidence.

This pipeline is responsible for:
  - Generating impact hypotheses from EvidenceBundle
  - Generating failure scenarios from hypotheses
  - Aggregating confidence and building evidence clusters

Output: InferenceResult
"""
from __future__ import annotations

from typing import Any

from core_engine.hypothesis.confidence_aggregator import ConfidenceAggregator
from core_engine.hypothesis.generator import HypothesisGenerator
from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.scenarios.generator import FailureScenarioGenerator


class InferenceResult:
    """Result of the inference pipeline.
    
    Attributes:
        hypotheses: Generated impact hypotheses.
        scenarios: Generated failure scenarios.
        evidence_clusters: Aggregated evidence clusters.
    """
    
    def __init__(
        self,
        hypotheses: list[dict[str, Any]],
        scenarios: list[dict[str, Any]],
        evidence_clusters: list[dict[str, Any]],
    ):
        self.hypotheses = hypotheses
        self.scenarios = scenarios
        self.evidence_clusters = evidence_clusters
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "hypotheses": self.hypotheses,
            "scenarios": self.scenarios,
            "evidence_clusters": self.evidence_clusters,
        }


class InferencePipeline:
    """Generates hypotheses and scenarios from evidence bundle.
    
    This pipeline reasons over the EvidenceBundle to produce probabilistic
    inferences about potential failures.
    """
    
    @staticmethod
    def run(bundle: EvidenceBundle) -> InferenceResult:
        """Run the inference pipeline.
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            
        Returns:
            InferenceResult containing hypotheses, scenarios, and clusters.
        """
        print("Running inference pipeline...")
        
        # Step 1: Generate hypotheses
        print("Generating impact hypotheses...")
        hypothesis_generator = HypothesisGenerator()
        hypotheses = hypothesis_generator.generate(bundle)
        hypotheses_list = [h.model_dump() for h in hypotheses]
        
        # Step 2: Generate scenarios from hypotheses
        print("Generating failure scenarios...")
        scenario_generator = FailureScenarioGenerator()
        scenarios = scenario_generator.generate(hypotheses)
        scenarios_list = [s.model_dump() for s in scenarios]
        
        # Step 3: Aggregate evidence clusters
        print("Aggregating evidence clusters...")
        aggregator = ConfidenceAggregator()
        aggregator.add_evidence_batch(bundle.impact_evidence)
        aggregator.calculate_all()
        
        # Build evidence clusters output
        evidence_clusters = []
        for cluster_key, cluster in aggregator._clusters.items():
            evidence_clusters.append({
                "source": cluster.source,
                "target": cluster.target,
                "evidence_count": cluster.evidence_count,
                "evidence_types": cluster.evidence_types,
                "base_confidence": cluster.base_confidence,
                "aggregated_confidence": cluster.aggregated_confidence,
            })
        
        print(f"Inference complete: {len(hypotheses_list)} hypotheses, "
              f"{len(scenarios_list)} scenarios, {len(evidence_clusters)} evidence clusters")
        
        return InferenceResult(
            hypotheses=hypotheses_list,
            scenarios=scenarios_list,
            evidence_clusters=evidence_clusters,
        )