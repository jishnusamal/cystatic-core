"""Confidence scorer — computes deterministic confidence for evidence objects."""

from __future__ import annotations

from typing import Dict, List, Set

from core_engine.models.evidence import (
    Signal,
    Evidence,
    ExecutionEvidence,
    CoverageEvidence,
    ArchitectureEvidence,
    CombinedEvidence,
)


class ConfidenceScorer:
    """Computes deterministic confidence scores for all evidence.

    Confidence is computed as follows:
    - Direct signals from rules: 1.0 (deterministic, from adapter)
    - Graph traversal paths: 0.92 (path existence is proven, but completeness depends on adapter)
    - Coverage analysis: 0.95 (test graph is reliable)
    - Architecture analysis: 0.92 (structural patterns are detected reliably)
    - Combined evidence: product of component confidences with decay
    - Missing/incomplete information: 0.5 (adapter may have missed something)
    """

    SIGNAL_CONFIDENCE = 1.0
    EXECUTION_CONFIDENCE = 0.92
    COVERAGE_CONFIDENCE = 0.95
    ARCHITECTURE_CONFIDENCE = 0.92
    COMBINED_DECAY = 0.9  # Multiplier per combination level

    def score_signal(self, signal: Signal) -> float:
        """Score a direct signal — always 1.0 for deterministic facts."""
        return self.SIGNAL_CONFIDENCE

    def score_execution_evidence(self, evidence: ExecutionEvidence) -> float:
        """Score execution evidence based on path completeness."""
        if not evidence.paths:
            return 0.5  # No paths found, uncertain
        # Confidence decreases slightly with more complex paths
        avg_path_length = sum(len(p.nodes) for p in evidence.paths) / max(len(evidence.paths), 1)
        complexity_penalty = min(0.1, avg_path_length / 100)
        return round(self.EXECUTION_CONFIDENCE - complexity_penalty, 2)

    def score_coverage_evidence(self, evidence: CoverageEvidence) -> float:
        """Score coverage evidence."""
        untested_count = (
            len(evidence.untested_entrypoints)
            + len(evidence.untested_persistence_paths)
            + len(evidence.untested_validation)
            + len(evidence.untested_transactions)
            + len(evidence.untested_migrations)
        )
        if untested_count == 0:
            return round(self.COVERAGE_CONFIDENCE, 2)
        # More untested paths = higher confidence we found real gaps
        return round(min(self.COVERAGE_CONFIDENCE + 0.03, 0.98), 2)

    def score_architecture_evidence(self, evidence: ArchitectureEvidence) -> float:
        """Score architecture evidence."""
        total_changes = (
            len(evidence.new_dependencies)
            + len(evidence.removed_dependencies)
            + len(evidence.new_database_access)
            + len(evidence.new_events)
            + len(evidence.new_apis)
            + len(evidence.new_service_calls)
            + len(evidence.new_cache_access)
            + len(evidence.cross_domain_interactions)
        )
        if total_changes == 0:
            return round(self.ARCHITECTURE_CONFIDENCE, 2)
        # More structural changes = more confident detection
        return round(min(self.ARCHITECTURE_CONFIDENCE + 0.03, 0.98), 2)

    def score_combined_evidence(self, evidence: CombinedEvidence) -> float:
        """Score combined evidence based on source signal confidences."""
        if not evidence.source_signals:
            return 0.5
        source_confidences = [s.confidence for s in evidence.source_signals]
        avg_confidence = sum(source_confidences) / len(source_confidences)
        # Apply decay for each combination level
        return round(avg_confidence * self.COMBINED_DECAY, 2)

    def build_confidence_summary(
        self,
        signals: List[Signal],
        execution: ExecutionEvidence | None = None,
        coverage: CoverageEvidence | None = None,
        architecture: ArchitectureEvidence | None = None,
        combined: List[CombinedEvidence] | None = None,
    ) -> Dict[str, float]:
        """Build a summary of all confidence scores."""
        summary: Dict[str, float] = {}

        if signals:
            # Average signal confidence
            summary["signals"] = round(
                sum(s.confidence for s in signals) / len(signals), 2
            )

        if execution:
            summary["execution_paths"] = self.score_execution_evidence(execution)

        if coverage:
            summary["coverage"] = self.score_coverage_evidence(coverage)

        if architecture:
            summary["architecture"] = self.score_architecture_evidence(architecture)

        if combined:
            summary["combined_evidence"] = round(
                sum(self.score_combined_evidence(c) for c in combined) / len(combined), 2
            )

        return summary