"""Signal combiner — combines low-level signals into higher-level evidence."""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from core_engine.models.evidence import Signal, CombinedEvidence


class SignalCombiner:
    """Combines related signals into higher-level combined evidence.

    Instead of:
        ValidationModified
        PersistenceWriteAdded
        TransactionChanged

    Produces:
        "Validation change reaches persistent state."

    This stage only combines evidence — no predictions, no invented facts.
    """

    # Signal groups that together form meaningful combined evidence
    COMBINATION_RULES: List[Tuple[str, List[str], str]] = [
        (
            "validation_reaches_persistence",
            ["ValidationModified", "PersistenceWriteAdded", "TransactionBoundaryChanged"],
            "Validation change reaches persistent state via transaction.",
        ),
        (
            "validation_reaches_persistence_no_tx",
            ["ValidationModified", "PersistenceWriteAdded"],
            "Validation change reaches persistent state (no transaction boundary).",
        ),
        (
            "new_api_no_validation",
            ["NewAPIEndpoint", "ValidationRemoved"],
            "New API endpoint with no validation.",
        ),
        (
            "new_api_external_call",
            ["NewAPIEndpoint", "NewExternalCall"],
            "New API endpoint makes external call.",
        ),
        (
            "unvalidated_write_path",
            ["ValidationRemoved", "PersistenceWriteAdded"],
            "Write path with reduced validation.",
        ),
        (
            "new_external_reachable_path",
            ["NewAPIEndpoint", "PersistenceWriteAdded"],
            "New externally reachable write path.",
        ),
        (
            "untested_validation_path",
            ["ValidationModified", "QuerySemanticsChanged"],
            "Validation changes affect query semantics — data integrity risk.",
        ),
        (
            "transaction_change_with_write",
            ["TransactionBoundaryChanged", "PersistenceWriteAdded"],
            "Transaction boundary changed around persistent write.",
        ),
        (
            "new_event_with_new_api",
            ["NewEventPublished", "NewAPIEndpoint"],
            "New API endpoint publishes new event.",
        ),
        (
            "cache_and_persistence",
            ["CacheWriteAdded", "PersistenceWriteAdded"],
            "New cache write alongside persistence write — cache consistency risk.",
        ),
        (
            "migration_without_test",
            ["MigrationAdded", "QuerySemanticsChanged"],
            "Migration may affect query results without test coverage.",
        ),
    ]

    def combine(self, signals: List[Signal]) -> List[CombinedEvidence]:
        """Combine signals into higher-level evidence."""
        signal_names = [s.name for s in signals]
        combined_evidence: List[CombinedEvidence] = []

        for rule_id, required_signals, description in self.COMBINATION_RULES:
            if all(sig_name in signal_names for sig_name in required_signals):
                matching_signals = [s for s in signals if s.name in required_signals]
                confidence = self._compute_combined_confidence(matching_signals)

                all_node_ids: List[str] = []
                all_edge_ids: List[str] = []
                for sig in matching_signals:
                    all_node_ids.extend(sig.node_ids)
                    all_edge_ids.extend(sig.edge_ids)

                combined_evidence.append(
                    CombinedEvidence(
                        description=description,
                        signals=matching_signals,
                        source_signals=matching_signals,
                        confidence=confidence,
                        node_ids=list(set(all_node_ids)),
                        edge_ids=list(set(all_edge_ids)),
                        properties={
                            "combination_rule": rule_id,
                            "signal_count": len(matching_signals),
                        },
                    )
                )

        # Deduplicate by description
        seen: Set[str] = set()
        deduplicated: List[CombinedEvidence] = []
        for ce in combined_evidence:
            if ce.description not in seen:
                seen.add(ce.description)
                deduplicated.append(ce)

        return deduplicated

    def _compute_combined_confidence(self, signals: List[Signal]) -> float:
        """Compute combined confidence from multiple signals.

        Uses a simple product-based approach — each signal's confidence
        multiplies, with diminishing returns for many signals.
        """
        if not signals:
            return 1.0

        # Start with the lowest confidence among signals
        confidences = [s.confidence for s in signals]
        base = min(confidences)

        # Apply diminishing returns for each additional signal
        # Each extra signal adds sqrt(confidence) instead of full confidence
        extra = sum(c for c in confidences) - base
        if extra > 0:
            # Combined confidence = base + adjusted extra
            # The more signals, the less each additional one adds
            adjusted = extra / (len(signals) ** 0.5)
            result = base * (1.0 - 0.1 * (len(signals) - 1))
            result = min(result + adjusted * 0.1, base)
            return max(round(result, 2), 0.5)

        return base