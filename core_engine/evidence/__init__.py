"""
Evidence compression package.

Provides progressive compression from raw evidence to high-confidence hypotheses:
  Raw Evidence → Deduplicated → Clustered → Scored → Pruned → Hypotheses → Scenarios
"""
from core_engine.evidence.scoring import EvidenceScorer, EVIDENCE_TYPE_BASE_SCORES
from core_engine.evidence.deduplicator import EvidenceDeduplicator
from core_engine.evidence.clusterer import EvidenceClusterer, EvidenceCluster
from core_engine.evidence.causal_chain import CausalChainVerifier
from core_engine.evidence.pruner import EvidencePruner
from core_engine.evidence.compression_pipeline import CompressionPipeline, CompressionResult

__all__ = [
    "EvidenceScorer",
    "EVIDENCE_TYPE_BASE_SCORES",
    "EvidenceDeduplicator",
    "EvidenceClusterer",
    "EvidenceCluster",
    "CausalChainVerifier",
    "EvidencePruner",
    "CompressionPipeline",
    "CompressionResult",
]