"""
Evidence Scoring — assigns weighted confidence scores to evidence items.

Every evidence item shouldn't have equal weight. Higher scores mean
stronger signals for downstream reasoning.

Base scores:
  Database write           → 0.95
  Transaction boundary     → 0.90
  REST endpoint            → 0.80
  Event publisher          → 0.70
  Import relationship      → 0.25
  Same directory           → 0.10
  Naming similarity        → 0.05
"""
from __future__ import annotations

from typing import Any

# Base confidence scores by evidence type (0.0 - 1.0)
# These reflect how strongly each type signals actual behavioral impact
EVIDENCE_TYPE_BASE_SCORES: dict[str, float] = {
    # Database interactions — highest confidence
    "writes_table": 0.95,
    "shares_table": 0.90,
    "reads_table": 0.70,
    "shared_database_table": 0.90,

    # Transaction boundaries
    "starts_transaction": 0.90,
    "commits_transaction": 0.90,
    "rolls_back_transaction": 0.90,
    "inside_transaction": 0.85,
    "shared_transaction": 0.90,

    # API / Endpoints
    "rest_endpoint": 0.80,
    "graphql_endpoint": 0.80,
    "grpc_endpoint": 0.80,
    "cli_endpoint": 0.70,
    "scheduled_endpoint": 0.75,
    "endpoint_implementation": 0.80,
    "canonical_request_flow": 0.85,

    # Events
    "publishes_event": 0.70,
    "consumes_event": 0.70,
    "shared_event": 0.65,
    "shared_event_publication": 0.70,
    "shared_event_consumption": 0.70,
    "event_publication_consumption": 0.80,

    # Cache
    "reads_cache": 0.60,
    "shared_cache": 0.65,
    "cache_dependency": 0.65,

    # Services
    "depends_on_service": 0.55,
    "same_service": 0.50,

    # Business objects
    "shared_business_object": 0.75,
    "business_object_reference": 0.70,

    # Domains
    "belongs_to_domain": 0.50,
    "touches_domain": 0.40,
    "cross_domain_relationship": 0.60,
    "shared_domain": 0.50,
    "domain_relationship": 0.60,

    # Ownership
    "owned_by": 0.45,
    "same_owner": 0.40,
    "cross_owner": 0.35,
    "ownership_relationship": 0.45,

    # External dependencies
    "calls_external_system": 0.55,
    "shared_external_system": 0.50,
    "depends_on_provider": 0.50,

    # Operational constraints
    "operational_constraint": 0.60,

    # Code-level
    "imports_symbol": 0.25,
    "imports_module": 0.20,
    "same_module": 0.15,
    "same_class": 0.20,
    "symbol_reference": 0.30,

    # Weak signals
    "naming_similarity": 0.05,

    # Ownership evidence types (backward compat)
    "same_module_owner": 0.40,
    "same_service_owner": 0.40,

    # Side effect signal multipliers
    "database_write": 0.85,
    "database_read": 0.50,
    "cache_operation": 0.60,
    "http_call": 0.55,
    "queue_publish": 0.65,
    "queue_consume": 0.65,
    "file_io": 0.30,
    "external_api": 0.55,
}

# Risk anchor boosts
RISK_ANCHOR_BOOSTS: dict[str, float] = {
    "money_flow": 0.15,
    "authentication": 0.12,
    "authorization": 0.12,
    "transaction_boundary": 0.10,
    "state_mutation": 0.10,
    "retry_sensitive": 0.08,
    "external_dependency": 0.08,
    "idempotency": 0.08,
    "cache_consistency": 0.05,
    "generic": 0.03,
}


class EvidenceScorer:
    """Assigns scores to evidence items based on type and context.

    The scorer:
    - Uses base scores from EVIDENCE_TYPE_BASE_SCORES
    - Applies risk anchor boosts if present
    - Returns a score in [0.0, 1.0]
    """

    @staticmethod
    def score_evidence(
        evidence_type: str,
        confidence: float = 1.0,
        risk_anchor_types: list[str] | None = None,
    ) -> float:
        """Score a single evidence item.

        Args:
            evidence_type: The type of evidence (see EVIDENCE_TYPE_BASE_SCORES).
            confidence: Existing confidence modifier (0.0-1.0).
            risk_anchor_types: Risk anchors present in the same context.

        Returns:
            Scaled score in [0.0, 1.0].
        """
        base = EVIDENCE_TYPE_BASE_SCORES.get(evidence_type, 0.10)
        score = base * confidence

        # Apply risk anchor boosts
        if risk_anchor_types:
            for atype in risk_anchor_types:
                boost = RISK_ANCHOR_BOOSTS.get(atype, 0.0)
                score += boost

        return max(0.0, min(1.0, score))

    @staticmethod
    def cluster_score(evidence_scores: list[float]) -> float:
        """Compute aggregate score for a cluster.

        Uses weighted average — higher scores contribute more.

        Args:
            evidence_scores: List of individual evidence scores.

        Returns:
            Aggregated cluster score in [0.0, 1.0].
        """
        if not evidence_scores:
            return 0.0

        # Weighted: square each score so high scores dominate
        weights = [s * s for s in evidence_scores]
        total_weight = sum(weights)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(s * w for s, w in zip(evidence_scores, weights))
        return max(0.0, min(1.0, weighted_sum / total_weight))

    @staticmethod
    def hypothesis_confidence(
        cluster_score: float,
        has_causal_chain: bool,
        evidence_count: int,
    ) -> float:
        """Compute final hypothesis confidence from cluster.

        Args:
            cluster_score: Aggregated cluster score.
            has_causal_chain: Whether a valid causal chain exists.
            evidence_count: Number of supporting evidence items.

        Returns:
            Confidence score in [0.0, 1.0].
        """
        confidence = cluster_score

        # Boost if causal chain is verified
        if has_causal_chain:
            confidence += 0.10

        # Boost for multiple supporting evidence items
        if evidence_count >= 3:
            confidence += 0.05
        elif evidence_count >= 5:
            confidence += 0.10

        # Penalize lone weak evidence
        if evidence_count == 1 and cluster_score < 0.3:
            confidence *= 0.5

        return max(0.0, min(1.0, confidence))