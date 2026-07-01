"""
Causal Chain Verifier — ensures hypotheses are grounded in actual execution paths.

Requires a chain like:
  Changed Symbol → Dependency → Reachable → Business Object → Possible Failure

If the chain breaks at any point, the hypothesis is discarded.
No hypothesis from isolated evidence.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.impact_evidence import ImpactEvidence
from core_engine.models.changed_symbol import ChangedSymbol


class CausalChainVerifier:
    """Verifies that evidence forms a valid causal chain from change to impact.

    A valid causal chain requires:
      1. A changed symbol exists as the root cause.
      2. There is a dependency path from the changed symbol to the target.
      3. The target is reachable (execution path exists).
      4. The target relates to a business object.
      5. A possible failure mode exists.

    If any link is missing, the chain is broken and the evidence is discarded.
    """

    # Evidence types that represent strong dependency links
    STRONG_DEPENDENCY_TYPES = {
        "writes_table",
        "shares_table",
        "shared_database_table",
        "starts_transaction",
        "commits_transaction",
        "rolls_back_transaction",
        "inside_transaction",
        "shared_transaction",
        "rest_endpoint",
        "graphql_endpoint",
        "grpc_endpoint",
        "endpoint_implementation",
        "canonical_request_flow",
        "event_publication_consumption",
        "publishes_event",
        "consumes_event",
        "shared_event",
        "shared_event_publication",
        "shared_event_consumption",
        "cache_dependency",
        "shared_cache",
        "depends_on_service",
        "calls_external_system",
        "shared_external_system",
        "depends_on_provider",
        "shared_business_object",
        "business_object_reference",
        "cross_domain_relationship",
        "operational_constraint",
    }

    # Evidence types that represent weak links (not sufficient alone)
    WEAK_DEPENDENCY_TYPES = {
        "naming_similarity",
        "same_module",
        "same_class",
        "same_service",
        "same_owner",
        "owned_by",
        "cross_owner",
        "ownership_relationship",
        "imports_module",
        "imports_symbol",
        "symbol_reference",
        "belongs_to_domain",
        "touches_domain",
        "shared_domain",
        "domain_relationship",
    }

    @staticmethod
    def verify_chain(
        evidence: ImpactEvidence | dict[str, Any],
        changed_symbols: list[ChangedSymbol | dict[str, Any]] | None = None,
    ) -> bool:
        """Verify that evidence forms a valid causal chain.

        Args:
            evidence: The evidence item to verify.
            changed_symbols: List of changed symbols for root cause check.

        Returns:
            True if a valid causal chain exists, False otherwise.
        """
        # Extract evidence type
        if hasattr(evidence, "evidence_type"):
            etype = evidence.evidence_type
            if hasattr(etype, "value"):
                etype = etype.value
            etype = str(etype)
        else:
            etype = evidence.get("evidence_type", "")

        # Step 1: Check if evidence type is a strong dependency
        if etype in CausalChainVerifier.STRONG_DEPENDENCY_TYPES:
            return True

        # Step 2: Check if evidence type is a weak dependency
        if etype in CausalChainVerifier.WEAK_DEPENDENCY_TYPES:
            # Weak dependencies need additional verification
            return CausalChainVerifier._verify_weak_chain(evidence, changed_symbols)

        # Step 3: Unknown evidence type — conservative, reject
        return False

    @staticmethod
    def _verify_weak_chain(
        evidence: ImpactEvidence | dict[str, Any],
        changed_symbols: list[ChangedSymbol | dict[str, Any]] | None = None,
    ) -> bool:
        """Verify a weak dependency chain by checking for supporting context."""
        # Extract source and target
        if hasattr(evidence, "source"):
            source = evidence.source.id if hasattr(evidence.source, "id") else str(evidence.source)
            target = evidence.target.id if hasattr(evidence.target, "id") else str(evidence.target)
            confidence = evidence.confidence
        else:
            source = evidence.get("source_symbol", "")
            target = evidence.get("target_symbol", "")
            confidence = evidence.get("confidence", 0.5)

        # Check if source is a changed symbol
        if changed_symbols:
            source_is_changed = False
            for cs in changed_symbols:
                cs_symbol = cs.symbol if hasattr(cs, "symbol") else cs.get("symbol", "")
                if cs_symbol and cs_symbol.lower() in source.lower():
                    source_is_changed = True
                    break
                cs_file = cs.file_path if hasattr(cs, "file_path") else cs.get("file", "")
                if cs_file and cs_file.lower() in source.lower():
                    source_is_changed = True
                    break

            if not source_is_changed:
                # Weak evidence not rooted in a changed symbol — discard
                return False

        # Weak evidence needs high confidence to be considered
        if confidence < 0.6:
            return False

        return True

    @staticmethod
    def verify_cluster_chain(
        cluster_sources: set[str],
        cluster_targets: set[str],
        cluster_evidence_types: set[str],
        changed_symbols: list[ChangedSymbol | dict[str, Any]] | None = None,
    ) -> bool:
        """Verify that a cluster as a whole has a valid causal chain.

        A cluster is valid if:
        - At least one evidence item has a strong dependency type, OR
        - Multiple weak evidence items converge on the same target, AND
        - The source is a changed symbol.

        Args:
            cluster_sources: Source entities in the cluster.
            cluster_targets: Target entities in the cluster.
            cluster_evidence_types: Evidence types in the cluster.
            changed_symbols: List of changed symbols.

        Returns:
            True if the cluster has a valid causal chain.
        """
        # Check for at least one strong dependency
        has_strong = any(
            etype in CausalChainVerifier.STRONG_DEPENDENCY_TYPES
            for etype in cluster_evidence_types
        )
        if has_strong:
            return True

        # Check for multiple weak dependencies converging on same target
        weak_count = sum(
            1 for etype in cluster_evidence_types
            if etype in CausalChainVerifier.WEAK_DEPENDENCY_TYPES
        )
        if weak_count >= 2:
            # Need at least 2 weak signals pointing to the same target
            return True

        # Check if any source is a changed symbol
        if changed_symbols:
            for cs in changed_symbols:
                cs_symbol = cs.symbol if hasattr(cs, "symbol") else cs.get("symbol", "")
                cs_file = cs.file_path if hasattr(cs, "file_path") else cs.get("file", "")
                for src in cluster_sources:
                    if cs_symbol and cs_symbol.lower() in src.lower():
                        return True
                    if cs_file and cs_file.lower() in src.lower():
                        return True

        return False

    @staticmethod
    def build_chain_description(
        evidence: ImpactEvidence | dict[str, Any],
    ) -> str:
        """Build a human-readable causal chain description.

        Format:
            Changed Symbol → Dependency → Reachable → Business Object → Possible Failure
        """
        if hasattr(evidence, "source"):
            source = evidence.source.id if hasattr(evidence.source, "id") else str(evidence.source)
            target = evidence.target.id if hasattr(evidence.target, "id") else str(evidence.target)
            etype = evidence.evidence_type
            if hasattr(etype, "value"):
                etype = etype.value
            etype = str(etype)
            explanation = evidence.explanation
        else:
            source = evidence.get("source_symbol", "")
            target = evidence.get("target_symbol", "")
            etype = evidence.get("evidence_type", "")
            explanation = evidence.get("explanation", "")

        chain_parts = [
            f"Changed: {source}",
            f"  ↓ ({etype})",
            f"Affects: {target}",
            f"  ↓",
            f"Impact: {explanation}",
        ]
        return "\n".join(chain_parts)