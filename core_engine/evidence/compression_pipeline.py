"""
CompressionPipeline — progressive evidence compression.

Implements the full compression pipeline:
  Changed Symbols → Raw Evidence → Deduplicate → Evidence Clusters → Score → Prune
  → Candidate Hypotheses → Rank + Filter → Failure Scenarios → Review → Verdict

Key design:
  - Evidence answers: "What did we observe?"
  - Clusters answer: "Which observations describe the same underlying concern?"
  - Hypotheses answer: "What could those observations mean?"
  - Scenarios answer: "How could that hypothesis manifest in production?"

The pipeline progressively compresses information instead of preserving it.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.impact_evidence import ImpactEvidence
from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.models.changed_symbol import ChangedSymbol
from core_engine.evidence.scoring import EvidenceScorer
from core_engine.evidence.deduplicator import EvidenceDeduplicator
from core_engine.evidence.clusterer import EvidenceClusterer, EvidenceCluster
from core_engine.evidence.causal_chain import CausalChainVerifier
from core_engine.evidence.pruner import EvidencePruner, PruningConfig


class CompressionResult:
    """Result of the compression pipeline.

    Attributes:
        raw_count: Number of raw evidence items input.
        deduplicated_group_count: Number of groups after deduplication.
        cluster_count: Number of semantic clusters after clustering.
        pruned_cluster_count: Number of clusters after pruning.
        hypothesis_count: Number of hypotheses generated.
        merged_hypothesis_count: Number of hypotheses after merging.
        simulation_count: Number of hypotheses selected for simulation.
        statistics: Detailed statistics at each pipeline stage.
    """

    def __init__(
        self,
        raw_count: int = 0,
        deduplicated_group_count: int = 0,
        cluster_count: int = 0,
        pruned_cluster_count: int = 0,
        hypothesis_count: int = 0,
        merged_hypothesis_count: int = 0,
        simulation_count: int = 0,
        statistics: dict[str, Any] | None = None,
    ):
        self.raw_count = raw_count
        self.deduplicated_group_count = deduplicated_group_count
        self.cluster_count = cluster_count
        self.pruned_cluster_count = pruned_cluster_count
        self.hypothesis_count = hypothesis_count
        self.merged_hypothesis_count = merged_hypothesis_count
        self.simulation_count = simulation_count
        self.statistics = statistics or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "raw_count": self.raw_count,
            "deduplicated_group_count": self.deduplicated_group_count,
            "cluster_count": self.cluster_count,
            "pruned_cluster_count": self.pruned_cluster_count,
            "hypothesis_count": self.hypothesis_count,
            "merged_hypothesis_count": self.merged_hypothesis_count,
            "simulation_count": self.simulation_count,
            "statistics": self.statistics,
        }

    def __repr__(self) -> str:
        return (
            f"CompressionResult(raw={self.raw_count}, "
            f"dedup_groups={self.deduplicated_group_count}, "
            f"clusters={self.cluster_count}, "
            f"pruned_clusters={self.pruned_cluster_count}, "
            f"hypotheses={self.hypothesis_count}, "
            f"merged={self.merged_hypothesis_count}, "
            f"for_simulation={self.simulation_count})"
        )


class CompressionPipeline:
    """Progressive evidence compression pipeline.

    Usage:
        pipeline = CompressionPipeline()
        result = pipeline.run(
            impact_evidence=[...],
            business_objects=[...],
            changed_symbols=[...],
            risk_anchor_types=[...],
        )
        # result.hypotheses contains high-confidence hypotheses
        # result.clusters contains pruned evidence clusters
        # result.statistics shows compression at each stage
    """

    def __init__(
        self,
        pruner: EvidencePruner | None = None,
        config: PruningConfig | None = None,
    ):
        self.pruner = pruner or EvidencePruner(config)

    def run(
        self,
        impact_evidence: list[ImpactEvidence | dict[str, Any]],
        business_objects: list[dict[str, Any]] | None = None,
        changed_symbols: list[ChangedSymbol | dict[str, Any]] | None = None,
        risk_anchor_types: list[str] | None = None,
    ) -> CompressionResult:
        """Run the full compression pipeline.

        Args:
            impact_evidence: Raw impact evidence from analyzers.
            business_objects: Business object metadata for compression.
            changed_symbols: List of changed symbols for causal verification.
            risk_anchor_types: Risk anchor types present in the change.

        Returns:
            CompressionResult with clustered, scored, pruned data.
        """
        raw_count = len(impact_evidence)

        # Stage 1: Deduplicate evidence before clustering
        evidence_groups = EvidenceDeduplicator.deduplicate(
            impact_evidence,
            business_objects=business_objects,
        )
        deduplicated_group_count = len(evidence_groups)

        # Stage 2: Cluster by propagation target (business objects / domains)
        clusters = EvidenceClusterer.cluster(
            evidence_groups,
            business_objects=business_objects,
            risk_anchor_types=risk_anchor_types,
        )
        cluster_count = len(clusters)

        # Stage 3: Verify causal chains for each cluster
        verified_clusters = []
        for cluster in clusters:
            if CausalChainVerifier.verify_cluster_chain(
                cluster.sources,
                cluster.targets,
                cluster.evidence_types,
                changed_symbols=changed_symbols,
            ):
                verified_clusters.append(cluster)
        cluster_count_after_chain = len(verified_clusters)

        # Stage 4: Prune low-quality clusters
        pruned_clusters = self.pruner.prune_clusters(verified_clusters)
        pruned_cluster_count = len(pruned_clusters)

        # Stage 5: Generate one hypothesis per cluster
        hypotheses = self._generate_hypotheses(
            pruned_clusters,
            business_objects=business_objects,
        )
        hypothesis_count = len(hypotheses)

        # Stage 6: Merge similar hypotheses
        merged_hypotheses = self.pruner.merge_hypotheses(hypotheses)
        merged_hypothesis_count = len(merged_hypotheses)

        # Stage 7: Select hypotheses for simulation (high-confidence only)
        simulation_candidates = self.pruner.prune_hypotheses(merged_hypotheses)
        simulation_count = len(simulation_candidates)

        # Build statistics
        statistics = {
            "raw_evidence_count": raw_count,
            "deduplicated_groups": deduplicated_group_count,
            "clusters_before_chain": cluster_count,
            "clusters_after_chain": cluster_count_after_chain,
            "clusters_after_pruning": pruned_cluster_count,
            "hypotheses_generated": hypothesis_count,
            "hypotheses_after_merge": merged_hypothesis_count,
            "hypotheses_for_simulation": simulation_count,
            "compression_ratio": (
                f"{raw_count} → {simulation_count}"
                f" ({self._compression_pct(raw_count, simulation_count):.1f}% reduction)"
            ),
            "discarded_by_chain": cluster_count - cluster_count_after_chain,
            "discarded_by_pruning": cluster_count_after_chain - pruned_cluster_count,
            "hypotheses_merged_into": hypothesis_count - merged_hypothesis_count,
            "hypotheses_below_simulation_threshold": merged_hypothesis_count - simulation_count,
        }

        # Attach results for downstream access
        self._last_result = {
            "clusters": [c.to_dict() for c in pruned_clusters],
            "all_hypotheses": merged_hypotheses,
            "simulation_candidates": simulation_candidates,
            "statistics": statistics,
        }

        return CompressionResult(
            raw_count=raw_count,
            deduplicated_group_count=deduplicated_group_count,
            cluster_count=cluster_count,
            pruned_cluster_count=pruned_cluster_count,
            hypothesis_count=hypothesis_count,
            merged_hypothesis_count=merged_hypothesis_count,
            simulation_count=simulation_count,
            statistics=statistics,
        )

    def get_clusters(self) -> list[dict[str, Any]]:
        """Get pruned clusters from the last run."""
        return getattr(self, "_last_result", {}).get("clusters", [])

    def get_hypotheses(self) -> list[dict[str, Any]]:
        """Get all merged hypotheses from the last run."""
        return getattr(self, "_last_result", {}).get("all_hypotheses", [])

    def get_simulation_candidates(self) -> list[dict[str, Any]]:
        """Get high-confidence hypotheses selected for simulation."""
        return getattr(self, "_last_result", {}).get("simulation_candidates", [])

    def get_statistics(self) -> dict[str, Any]:
        """Get compression statistics from the last run."""
        return getattr(self, "_last_result", {}).get("statistics", {})

    @staticmethod
    def _generate_hypotheses(
        clusters: list[EvidenceCluster],
        business_objects: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate one hypothesis per cluster.

        Each hypothesis explains all evidence in the cluster.
        This replaces the old approach of one hypothesis per evidence item.

        Args:
            clusters: Pruned evidence clusters.
            business_objects: Business object metadata.

        Returns:
            List of hypothesis dicts (one per cluster).
        """
        hypotheses = []

        for cluster in clusters:
            # Build a consolidated hypothesis from all evidence in the cluster
            hypothesis = CompressionPipeline._cluster_to_hypothesis(cluster)
            if hypothesis:
                hypotheses.append(hypothesis)

        # Sort by confidence descending
        hypotheses.sort(key=lambda h: h.get("confidence", 0.0), reverse=True)

        return hypotheses

    @staticmethod
    def _cluster_to_hypothesis(
        cluster: EvidenceCluster,
    ) -> dict[str, Any] | None:
        """Convert a single evidence cluster into one hypothesis.

        This generates one hypothesis that explains ALL evidence in the cluster,
        rather than one hypothesis per evidence item.

        Args:
            cluster: The evidence cluster.

        Returns:
            Hypothesis dict or None if cluster is too weak.
        """
        # Compute hypothesis confidence
        has_chain = CausalChainVerifier.verify_cluster_chain(
            cluster.sources,
            cluster.targets,
            cluster.evidence_types,
        )
        hypothesis_confidence = EvidenceScorer.hypothesis_confidence(
            cluster_score=cluster.cluster_score,
            has_causal_chain=has_chain,
            evidence_count=cluster.evidence_count,
        )

        # Generate consolidated description
        description = CompressionPipeline._build_hypothesis_description(cluster)

        # Determine impact type from strongest evidence types
        impact_type = CompressionPipeline._determine_impact_type(cluster.evidence_types)

        # Collect supporting evidence summaries (handle both ImpactEvidence and dict)
        evidence_facts = []
        for e in cluster.evidence:
            if hasattr(e, "explanation"):
                evidence_facts.append(e.explanation)
            elif isinstance(e, dict):
                evidence_facts.append(e.get("explanation", ""))
            else:
                evidence_facts.append("")

        return {
            "hypothesis": description,
            "cluster_id": cluster.cluster_id,
            "cluster_label": cluster.label,
            "confidence": round(hypothesis_confidence, 3),
            "impact_type": impact_type,
            "source_symbol": ", ".join(sorted(cluster.sources)),
            "target_symbol": ", ".join(sorted(cluster.targets)),
            "description": description,
            "evidence_summary": " | ".join(evidence_facts[:5]),
            "evidence_count": cluster.evidence_count,
            "evidence_types": sorted(cluster.evidence_types),
            "cluster_score": cluster.cluster_score,
            "has_causal_chain": has_chain,
            "affected_business_objects": [cluster.business_object] if cluster.business_object else [],
            "affected_domains": [cluster.domain] if cluster.domain else [],
            "risk_anchor_types": cluster.risk_anchor_types,
            "supporting_evidence_count": cluster.evidence_count,
        }

    @staticmethod
    def _build_hypothesis_description(cluster: EvidenceCluster) -> str:
        """Build a consolidated hypothesis from all evidence in a cluster."""
        parts = []

        if cluster.business_object:
            parts.append(f"Change affecting {cluster.business_object}")

        if cluster.domain:
            parts.append(f"in {cluster.domain} domain")

        # Describe the types of operations involved
        operation_descriptions = {
            "database_operation": "database operations",
            "transaction_operation": "transaction boundaries",
            "event_operation": "event processing",
            "cache_operation": "cache operations",
        }

        operations = []
        for etype in cluster.evidence_types:
            # Map evidence type to human-readable operation
            if "write" in etype or "writes" in etype:
                operations.append("database writes")
            elif "read" in etype or "reads" in etype:
                operations.append("database reads")
            elif "transaction" in etype:
                operations.append("transaction changes")
            elif "event" in etype:
                operations.append("event flow changes")
            elif "endpoint" in etype:
                operations.append("API endpoint changes")
            elif "cache" in etype:
                operations.append("cache operations")
            elif "external" in etype or "service" in etype:
                operations.append("external service dependencies")

        if operations:
            # Deduplicate while preserving order
            seen = set()
            unique_ops = []
            for op in operations:
                if op not in seen:
                    seen.add(op)
                    unique_ops.append(op)
            parts.append(f"involving {', '.join(unique_ops)}")

        parts.append("may cause production impact")

        return " — ".join(parts) if parts else f"Cluster {cluster.label}: potential impact"

    @staticmethod
    def _determine_impact_type(evidence_types: set[str]) -> str:
        """Determine the most likely impact type from evidence types in a cluster."""
        type_mapping = {
            "writes_table": "data_coupling",
            "reads_table": "data_coupling",
            "shares_table": "data_coupling",
            "shared_database_table": "data_coupling",
            "starts_transaction": "transaction_impact",
            "commits_transaction": "transaction_impact",
            "rolls_back_transaction": "transaction_impact",
            "inside_transaction": "transaction_impact",
            "shared_transaction": "transaction_impact",
            "rest_endpoint": "api_coupling",
            "graphql_endpoint": "api_coupling",
            "grpc_endpoint": "api_coupling",
            "endpoint_implementation": "api_coupling",
            "publishes_event": "event_coupling",
            "consumes_event": "event_coupling",
            "shared_event": "event_coupling",
            "shared_event_publication": "event_coupling",
            "shared_event_consumption": "event_coupling",
            "event_publication_consumption": "event_coupling",
            "cache_dependency": "consistency_impact",
            "shared_cache": "consistency_impact",
            "reads_cache": "consistency_impact",
            "depends_on_service": "dependency_impact",
            "calls_external_system": "dependency_impact",
            "shared_external_system": "dependency_impact",
            "depends_on_provider": "dependency_impact",
            "money_flow": "financial_impact",
            "authentication": "security_impact",
            "authorization": "security_impact",
            "shared_business_object": "domain_coupling",
            "business_object_reference": "domain_coupling",
            "cross_domain_relationship": "domain_coupling",
            "operational_constraint": "reliability_impact",
            "naming_similarity": "semantic_coupling",
            "imports_symbol": "dependency_coupling",
            "imports_module": "dependency_coupling",
        }

        # Check each evidence type in priority order
        for etype in evidence_types:
            if etype in type_mapping:
                return type_mapping[etype]

        return "unknown_impact"

    @staticmethod
    def _compression_pct(original: int, final: int) -> float:
        """Calculate compression percentage."""
        if original == 0:
            return 100.0
        return ((original - final) / original) * 100.0