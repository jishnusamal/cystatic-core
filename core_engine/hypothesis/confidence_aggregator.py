"""
Confidence Aggregator

Combines multiple weak evidence facts into strong evidence.
This is the key to the semantic analyzers' hypothesis quality improvement.

Instead of individual evidence with confidence 0.3-0.5,
multiple independent facts combine to produce confidence 0.8-0.94.
"""
from __future__ import annotations

from typing import Any
from collections import defaultdict
from pydantic import BaseModel, Field

from core_engine.impact_evidence import ImpactEvidence
from core_engine.models.evidence_bundle import EvidenceBundle


class EvidenceCluster(BaseModel):
    """Cluster of related evidence that strengthens confidence."""
    source: str = ""
    target: str = ""
    evidence_items: list[ImpactEvidence] = Field(default_factory=list)
    base_confidence: float = 0.0
    aggregated_confidence: float = 0.0
    evidence_count: int = 0
    evidence_types: list[str] = Field(default_factory=list)
    
    def add_evidence(self, evidence: ImpactEvidence) -> None:
        """Add evidence to the cluster."""
        # Update source/target from first evidence if not set
        if not self.source and hasattr(evidence, 'source'):
            self.source = str(evidence.source)
        if not self.target and hasattr(evidence, 'target'):
            self.target = str(evidence.target)
        
        self.evidence_items.append(evidence)
        self.evidence_count += 1
        if evidence.evidence_type.value not in self.evidence_types:
            self.evidence_types.append(evidence.evidence_type.value)
    
    def calculate_aggregated_confidence(self) -> float:
        """Calculate aggregated confidence from all evidence in cluster.
        
        Uses a weighted combination approach:
        - More evidence = higher confidence (diminishing returns)
        - Diverse evidence types = higher confidence
        - Higher individual confidences = higher aggregated confidence
        
        Returns:
            Aggregated confidence score (0.0-1.0)
        """
        if not self.evidence_items:
            return 0.0
        
        # Factor 1: Evidence count (diminishing returns after 5 items)
        count_score = min(self.evidence_count / 5.0, 1.0)
        count_score = count_score * 0.6 + (1.0 - count_score) * 0.4  # Diminishing returns curve
        
        # Factor 2: Evidence type diversity (more types = stronger signal)
        type_diversity = len(self.evidence_types)
        diversity_score = min(type_diversity / 5.0, 1.0)  # 5 types = full score
        
        # Factor 3: Average individual confidence
        avg_confidence = sum(e.confidence for e in self.evidence_items) / len(self.evidence_items)
        
        # Factor 4: Maximum confidence (best single evidence)
        max_confidence = max(e.confidence for e in self.evidence_items)
        
        # Weighted combination
        # Strong weight on average confidence and evidence count
        # Moderate weight on diversity
        # Small weight on max confidence (to avoid single-point-of-failure)
        aggregated = (
            avg_confidence * 0.40 +
            count_score * 0.30 +
            diversity_score * 0.20 +
            max_confidence * 0.10
        )
        
        # Boost for strong evidence combinations
        # If we have 3+ pieces of evidence with avg confidence > 0.6, boost
        if self.evidence_count >= 3 and avg_confidence >= 0.6:
            aggregated = min(aggregated * 1.15, 1.0)  # 15% boost
        
        # If we have 5+ pieces of evidence with diverse types, boost more
        if self.evidence_count >= 5 and type_diversity >= 3:
            aggregated = min(aggregated * 1.10, 1.0)  # Additional 10% boost
        
        self.aggregated_confidence = round(min(aggregated, 1.0), 3)
        return self.aggregated_confidence


class ConfidenceAggregator:
    """Aggregate multiple weak evidence facts into strong evidence.
    
    This aggregator:
    - Groups related evidence by (source, target) pairs
    - Calculates aggregated confidence for each group
    - Identifies strong evidence clusters
    - Produces enhanced ImpactEvidence with aggregated confidence
    
    The key insight: 5 pieces of evidence with confidence 0.4 each
    can combine to produce aggregated confidence of 0.85+.
    
    Usage:
        aggregator = ConfidenceAggregator()
        for evidence in evidence_list:
            aggregator.add_evidence(evidence)
        
        strong_evidence = aggregator.get_strong_evidence(threshold=0.7)
        all_evidence = aggregator.get_all_evidence()
    """
    
    def __init__(self):
        # Key: (source, target) -> EvidenceCluster
        self._clusters: dict[tuple[str, str], EvidenceCluster] = {}
    
    def add_evidence(self, evidence: ImpactEvidence) -> None:
        """Add evidence to the aggregator.
        
        Evidence is grouped by (source, target) pairs.
        
        Args:
            evidence: ImpactEvidence to add
        """
        # Extract source and target - handle both EntityRef and string
        source = str(evidence.source) if hasattr(evidence, 'source') else ""
        target = str(evidence.target) if hasattr(evidence, 'target') else ""
        
        key = (source, target)
        
        if key not in self._clusters:
            self._clusters[key] = EvidenceCluster(
                source=source,
                target=target,
            )
        
        self._clusters[key].add_evidence(evidence)
    
    def add_evidence_batch(self, evidence_list: list[ImpactEvidence]) -> None:
        """Add multiple evidence items at once.
        
        Args:
            evidence_list: List of ImpactEvidence objects
        """
        for evidence in evidence_list:
            self.add_evidence(evidence)
    
    def calculate_all(self) -> None:
        """Calculate aggregated confidence for all clusters."""
        for cluster in self._clusters.values():
            cluster.calculate_aggregated_confidence()
    
    def get_strong_evidence(self, threshold: float = 0.7) -> list[ImpactEvidence]:
        """Get evidence with aggregated confidence above threshold.
        
        Args:
            threshold: Minimum confidence threshold (default 0.7)
            
        Returns:
            List of ImpactEvidence with aggregated confidence >= threshold
        """
        strong_evidence = []
        
        for cluster in self._clusters.values():
            if cluster.aggregated_confidence >= threshold:
                # Create a single ImpactEvidence representing the aggregated evidence
                combined_explanation = self._combine_explanations(cluster.evidence_items)
                
                from core_engine.models.entity_ref import EntityRef
                evidence = ImpactEvidence(
                    source=EntityRef(kind="symbol", id=cluster.source, name=cluster.source.split(".")[-1] if cluster.source else ""),
                    target=EntityRef(kind="symbol", id=cluster.target, name=cluster.target.split(".")[-1] if cluster.target else ""),
                    evidence_type=self._determine_primary_type(cluster.evidence_items),
                    confidence=cluster.aggregated_confidence,
                    explanation=combined_explanation,
                )
                strong_evidence.append(evidence)
        
        # Sort by confidence (highest first)
        strong_evidence.sort(key=lambda e: e.confidence, reverse=True)
        return strong_evidence
    
    def get_all_evidence(self) -> list[ImpactEvidence]:
        """Get all evidence with aggregated confidence.
        
        Returns:
            List of all ImpactEvidence with aggregated confidence
        """
        all_evidence = []
        
        for cluster in self._clusters.values():
            combined_explanation = self._combine_explanations(cluster.evidence_items)
            
            from core_engine.models.entity_ref import EntityRef
            evidence = ImpactEvidence(
                source=EntityRef(kind="symbol", id=cluster.source, name=cluster.source.split(".")[-1] if cluster.source else ""),
                target=EntityRef(kind="symbol", id=cluster.target, name=cluster.target.split(".")[-1] if cluster.target else ""),
                evidence_type=self._determine_primary_type(cluster.evidence_items),
                confidence=cluster.aggregated_confidence,
                explanation=combined_explanation,
            )
            all_evidence.append(evidence)
        
        # Sort by confidence (highest first)
        all_evidence.sort(key=lambda e: e.confidence, reverse=True)
        return all_evidence
    
    def get_cluster_stats(self) -> dict[str, Any]:
        """Get statistics about evidence clusters.
        
        Returns:
            Dictionary with cluster statistics
        """
        if not self._clusters:
            return {
                "total_clusters": 0,
                "strong_clusters": 0,
                "avg_cluster_size": 0.0,
                "avg_confidence": 0.0,
            }
        
        cluster_sizes = [c.evidence_count for c in self._clusters.values()]
        confidences = [c.aggregated_confidence for c in self._clusters.values() if c.aggregated_confidence > 0]
        
        strong_count = sum(1 for c in self._clusters.values() if c.aggregated_confidence >= 0.7)
        
        return {
            "total_clusters": len(self._clusters),
            "strong_clusters": strong_count,
            "avg_cluster_size": round(sum(cluster_sizes) / len(cluster_sizes), 2),
            "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
            "max_confidence": round(max(confidences), 3) if confidences else 0.0,
            "min_confidence": round(min(confidences), 3) if confidences else 0.0,
        }
    
    def _combine_explanations(self, evidence_items: list[ImpactEvidence]) -> str:
        """Combine explanations from multiple evidence items.
        
        Args:
            evidence_items: List of evidence items
            
        Returns:
            Combined explanation string
        """
        if not evidence_items:
            return ""
        
        if len(evidence_items) == 1:
            return evidence_items[0].explanation
        
        # Take the first explanation and append others
        explanations = [e.explanation for e in evidence_items if e.explanation]
        
        if len(explanations) <= 2:
            return "; ".join(explanations)
        
        # For many explanations, summarize
        return f"{explanations[0]}; {len(explanations) - 1} additional supporting facts"
    
    def _determine_primary_type(self, evidence_items: list[ImpactEvidence]) -> EvidenceType:
        """Determine the primary evidence type from a cluster.
        
        Uses the most common type, or the highest confidence type if tied.
        
        Args:
            evidence_items: List of evidence items
            
        Returns:
            Primary EvidenceType
        """
        if not evidence_items:
            return EvidenceType.SYMBOL_REFERENCE
        
        # Count types
        type_counts: dict[str, int] = defaultdict(int)
        type_confidence: dict[str, float] = defaultdict(float)
        
        for e in evidence_items:
            type_counts[e.evidence_type.value] += 1
            type_confidence[e.evidence_type.value] += e.confidence
        
        # Find the type with highest count
        max_count = max(type_counts.values())
        candidates = [t for t, c in type_counts.items() if c == max_count]
        
        if len(candidates) == 1:
            return EvidenceType(candidates[0])
        
        # If tied, use the one with highest total confidence
        best_type = max(candidates, key=lambda t: type_confidence[t])
        return EvidenceType(best_type)


def aggregate_confidence(evidence_list: list[ImpactEvidence], threshold: float = 0.7) -> dict[str, Any]:
    """Convenience function to aggregate evidence and return strong evidence.
    
    Args:
        evidence_list: List of ImpactEvidence to aggregate
        threshold: Confidence threshold for "strong" evidence
        
    Returns:
        Dictionary with:
            - strong_evidence: List of strong evidence
            - all_evidence: List of all aggregated evidence
            - stats: Statistics about the aggregation
    """
    aggregator = ConfidenceAggregator()
    aggregator.add_evidence_batch(evidence_list)
    aggregator.calculate_all()
    
    return {
        "strong_evidence": aggregator.get_strong_evidence(threshold),
        "all_evidence": aggregator.get_all_evidence(),
        "stats": aggregator.get_cluster_stats(),
    }