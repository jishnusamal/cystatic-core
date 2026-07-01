"""
Evidence Pruner — aggressively discards low-value evidence at every pipeline stage.

Design principle: not every piece of evidence deserves a hypothesis.
Aggressive pruning is a feature, not a bug.

Pruning rules:
  1. If confidence < threshold → discard()
  2. If cluster size == 1 and score < 0.3 → discard()
  3. If not reachable → discard()
  4. If no business impact → discard()
"""
from __future__ import annotations

from typing import Any

from core_engine.evidence.clusterer import EvidenceCluster


class PruningConfig:
    """Configuration for evidence pruning thresholds."""

    def __init__(
        self,
        min_evidence_score: float = 0.05,
        min_cluster_score: float = 0.15,
        min_cluster_size_for_low_score: int = 2,
        low_score_threshold: float = 0.30,
        min_hypothesis_confidence: float = 0.40,
        simulation_confidence_threshold: float = 0.60,
    ):
        self.min_evidence_score = min_evidence_score
        self.min_cluster_score = min_cluster_score
        self.min_cluster_size_for_low_score = min_cluster_size_for_low_score
        self.low_score_threshold = low_score_threshold
        self.min_hypothesis_confidence = min_hypothesis_confidence
        self.simulation_confidence_threshold = simulation_confidence_threshold


class EvidencePruner:
    """Prunes evidence, clusters, and hypotheses based on quality thresholds.

    Default configuration implements the task recommendations:
    - min_evidence_score=0.05: Discard near-zero signals (naming similarity alone)
    - min_cluster_score=0.15: Discard very weak clusters
    - min_cluster_size_for_low_score=2: Lone evidence below 0.30 is discarded
    - min_hypothesis_confidence=0.40: Low-confidence hypotheses never become scenarios
    - simulation_confidence_threshold=0.60: Only simulate high-confidence hypotheses
    """

    def __init__(self, config: PruningConfig | None = None):
        self.config = config or PruningConfig()

    def prune_evidence(
        self,
        evidence_list: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Prune low-quality evidence items.

        Args:
            evidence_list: List of evidence dicts with 'confidence' and 'evidence_type'.

        Returns:
            Filtered evidence list.
        """
        pruned = []
        discarded_count = 0

        for evidence in evidence_list:
            score = evidence.get("_score", evidence.get("confidence", 0.5))
            etype = evidence.get("evidence_type", "")
            confidence = evidence.get("confidence", 0.5)

            # Rule: Discard if base score is too low
            if score < self.config.min_evidence_score:
                discarded_count += 1
                continue

            # Rule: Discard naming_similarity alone without context
            if etype == "naming_similarity" and confidence < 0.5:
                discarded_count += 1
                continue

            pruned.append(evidence)

        return pruned

    def prune_clusters(
        self,
        clusters: list[EvidenceCluster],
    ) -> list[EvidenceCluster]:
        """Prune low-quality clusters.

        Args:
            clusters: List of EvidenceCluster objects.

        Returns:
            Filtered cluster list.
        """
        pruned = []
        discarded_count = 0

        for cluster in clusters:
            # Rule: Discard if cluster score is too low
            if cluster.cluster_score < self.config.min_cluster_score:
                discarded_count += 1
                continue

            # Rule: Single evidence with low score → discard
            if (
                cluster.evidence_count <= self.config.min_cluster_size_for_low_score
                and cluster.cluster_score < self.config.low_score_threshold
            ):
                discarded_count += 1
                continue

            pruned.append(cluster)

        return pruned

    def prune_hypotheses(
        self,
        hypotheses: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Prune low-confidence hypotheses from scenario generation.

        Only hypotheses with confidence >= simulation_confidence_threshold
        proceed to simulation. Others stay as supporting evidence.

        Args:
            hypotheses: List of hypothesis dicts.

        Returns:
            Filtered hypotheses for simulation.
        """
        return [
            h for h in hypotheses
            if h.get("confidence", 0.0) >= self.config.simulation_confidence_threshold
        ]

    def should_simulate(self, hypothesis: dict[str, Any]) -> bool:
        """Check if a hypothesis should be simulated.

        Implements: hypothesis.confidence >= 0.75 (or configured threshold)
        Everything else stays as supporting evidence.

        Args:
            hypothesis: Hypothesis dict.

        Returns:
            True if hypothesis should proceed to simulation.
        """
        confidence = hypothesis.get("confidence", 0.0)
        return confidence >= self.config.simulation_confidence_threshold

    def merge_hypotheses(
        self,
        hypotheses: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge similar hypotheses into one consolidated hypothesis.

        Identifies groups like:
          "User update may fail"
          "User cache may become stale"
          "User API may return old data"
        
        And merges into: "User state inconsistency after update"

        Args:
            hypotheses: List of hypothesis dicts.

        Returns:
            Merged hypothesis list.
        """
        if not hypotheses:
            return []

        merged: dict[str, dict[str, Any]] = {}
        
        for hypothesis in hypotheses:
            # Build a merge key from business objects and impact type
            bos = hypothesis.get("affected_business_objects", [])
            impact_type = hypothesis.get("impact_type", "unknown_impact")
            
            # Use first business object + impact type as merge key
            merge_key = f"{bos[0]}:{impact_type}" if bos else impact_type
            
            if merge_key not in merged:
                merged[merge_key] = dict(hypothesis)
                merged[merge_key]["merged_from"] = [hypothesis.get("hypothesis", "")]
                merged[merge_key]["merged_count"] = 1
            else:
                existing = merged[merge_key]
                # Take the highest confidence
                if hypothesis.get("confidence", 0.0) > existing.get("confidence", 0.0):
                    existing["confidence"] = hypothesis.get("confidence", 0.0)
                
                # Combine evidence summaries
                existing_summary = existing.get("evidence_summary", "")
                new_summary = hypothesis.get("evidence_summary", "")
                if new_summary and new_summary not in existing_summary:
                    existing["evidence_summary"] = f"{existing_summary}; {new_summary}"
                
                # Track merge sources
                existing.setdefault("merged_from", []).append(hypothesis.get("hypothesis", ""))
                existing["merged_count"] = existing.get("merged_count", 1) + 1
                
                # Aggregate business objects
                existing_bos = set(existing.get("affected_business_objects", []))
                new_bos = set(hypothesis.get("affected_business_objects", []))
                existing["affected_business_objects"] = sorted(existing_bos | new_bos)
                
                # Aggregate domains
                existing_domains = set(existing.get("affected_domains", []))
                new_domains = set(hypothesis.get("affected_domains", []))
                existing["affected_domains"] = sorted(existing_domains | new_domains)
        
        return list(merged.values())