"""
InferencePipeline — generates hypotheses and scenarios from evidence.

This pipeline is responsible for:
  - Progressive evidence compression (deduplicate, cluster, score, prune)
  - Generating impact hypotheses from compressed evidence
  - Generating failure scenarios ONLY from high-confidence hypotheses

Output: InferenceResult

Progressive compression pipeline:
  Changed Symbols → Raw Evidence → Deduplicate → Evidence Clusters
  → Score + Causal Chain Check → Prune → Candidate Hypotheses
  → Merge → Rank + Filter → Failure Scenarios → Review → Verdict
"""
from __future__ import annotations

from typing import Any

from core_engine.hypothesis.generator import HypothesisGenerator
from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.scenarios.generator import FailureScenarioGenerator
from core_engine.evidence.compression_pipeline import (
    CompressionPipeline,
    CompressionResult,
)
from core_engine.evidence.pruner import EvidencePruner, PruningConfig


class InferenceResult:
    """Result of the inference pipeline.
    
    Attributes:
        hypotheses: Generated impact hypotheses (merged, ranked).
        scenarios: Generated failure scenarios (high-confidence only).
        evidence_clusters: Aggregated and pruned evidence clusters.
        compression: Compression statistics from the pipeline.
    """
    
    def __init__(
        self,
        hypotheses: list[dict[str, Any]],
        scenarios: list[dict[str, Any]],
        evidence_clusters: list[dict[str, Any]],
        compression: CompressionResult | None = None,
    ):
        self.hypotheses = hypotheses
        self.scenarios = scenarios
        self.evidence_clusters = evidence_clusters
        self.compression = compression
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "hypotheses": self.hypotheses,
            "scenarios": self.scenarios,
            "evidence_clusters": self.evidence_clusters,
            "compression": self.compression.to_dict() if self.compression else None,
        }


class InferencePipeline:
    """Generates hypotheses and scenarios from evidence bundle.
    
    This pipeline uses progressive compression to reduce thousands of
    evidence items into a small number of high-confidence scenarios.
    
    Compression flow:
      1. Deduplicate equivalent evidence
      2. Cluster by business object / domain / flow
      3. Score each cluster
      4. Verify causal chains
      5. Prune low-quality clusters
      6. Generate one hypothesis per cluster
      7. Merge similar hypotheses
      8. Select high-confidence hypotheses for simulation
    """
    
    def __init__(
        self,
        simulation_threshold: float = 0.60,
        config: PruningConfig | None = None,
    ):
        """Initialize with optional pruning configuration.
        
        Args:
            simulation_threshold: Confidence threshold for simulation (default 0.60).
                Only hypotheses at or above this threshold become scenarios.
            config: Custom pruning configuration.
        """
        self.simulation_threshold = simulation_threshold
        if config:
            config.simulation_confidence_threshold = simulation_threshold
        self.compression_pipeline = CompressionPipeline(config=config)
    
    @staticmethod
    def run(bundle: EvidenceBundle) -> InferenceResult:
        """Run the inference pipeline.
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            
        Returns:
            InferenceResult containing hypotheses, scenarios, and clusters.
        """
        pipeline = InferencePipeline()
        
        print("Running inference pipeline with progressive compression...")
        
        # Step 1-4: Run progressive compression pipeline
        # Deduplicate → Cluster → Score → Causal Chain → Prune → Hypotheses → Merge
        print("Compressing evidence...")
        compression_result = pipeline.compression_pipeline.run(
            impact_evidence=bundle.impact_evidence,
            business_objects=[bo.model_dump() if hasattr(bo, "model_dump") else bo
                            for bo in bundle.business_objects],
            changed_symbols=bundle.changed_symbols,
            risk_anchor_types=[ra.anchor_type.value if hasattr(ra.anchor_type, "value") else str(ra.anchor_type)
                             for ra in bundle.risk_anchors],
        )
        
        # Get compressed hypotheses
        all_hypotheses = pipeline.compression_pipeline.get_hypotheses()
        simulation_candidates = pipeline.compression_pipeline.get_simulation_candidates()
        clusters = pipeline.compression_pipeline.get_clusters()
        statistics = pipeline.compression_pipeline.get_statistics()
        
        # Step 5: Generate failure scenarios ONLY from high-confidence hypotheses
        print(f"Generating failure scenarios ({len(simulation_candidates)} high-confidence hypotheses)...")
        scenario_generator = FailureScenarioGenerator()
        
        # Convert dict hypotheses to ImpactHypothesis objects for scenario generator
        from core_engine.models.impact_hypothesis import ImpactHypothesis
        hypothesis_objects = []
        for h in simulation_candidates:
            try:
                hypothesis_objects.append(ImpactHypothesis(
                    hypothesis=h.get("hypothesis", ""),
                    confidence=h.get("confidence", 0.5),
                    source_symbol=h.get("source_symbol", ""),
                    target_symbol=h.get("target_symbol", ""),
                    impact_type=h.get("impact_type", "unknown_impact"),
                    description=h.get("description", ""),
                    evidence_summary=h.get("evidence_summary", ""),
                    affected_business_objects=h.get("affected_business_objects", []),
                    affected_domains=h.get("affected_domains", []),
                ))
            except Exception as e:
                print(f"Warning: could not convert hypothesis: {e}")
                continue
        
        scenarios = scenario_generator.generate(hypothesis_objects)
        scenarios_list = [s.model_dump() for s in scenarios]
        
        # Print compression statistics
        print(f"\n=== Compression Statistics ===")
        for key, value in statistics.items():
            if key != "compression_ratio":
                print(f"  {key}: {value}")
        print(f"  {statistics.get('compression_ratio', 'N/A')}")
        print(f"")
        print(f"Scenarios generated: {len(scenarios_list)}")
        
        return InferenceResult(
            hypotheses=all_hypotheses,
            scenarios=scenarios_list,
            evidence_clusters=clusters,
            compression=compression_result,
        )
