"""Packet builder — constructs the final evidence packet for the LLM."""

from __future__ import annotations

from typing import Dict, List, Set

from core_engine.models.semantic_graph import ValidatedSemanticGraph
from core_engine.models.evidence import (
    Signal,
    ExecutionPath,
    ExecutionEvidence,
    CoverageEvidence,
    ArchitectureEvidence,
    CombinedEvidence,
)
from core_engine.models.packet import EvidencePacket
from core_engine.inference.rule_runner import RuleRunner
from core_engine.inference.signal_combiner import SignalCombiner
from core_engine.inference.confidence import ConfidenceScorer
from core_engine.analyzers.execution_paths import ExecutionPathAnalyzer
from core_engine.analyzers.coverage_analyzer import CoverageAnalyzer
from core_engine.analyzers.architecture_analyzer import ArchitectureAnalyzer
from core_engine.analyzers.impact_analyzer import ImpactAnalyzer
from core_engine.packet.compressor import PacketCompressor


class PacketBuilder:
    """Builds the final evidence packet from a validated semantic graph.

    Orchestrates:
    1. Rule engine — run all rules
    2. Signal combination — combine related signals
    3. Graph analysis — execution paths, impact, coverage, architecture
    4. Confidence scoring — compute deterministic confidence
    5. Compression — deduplicate, merge, optimize
    6. Packet assembly — construct the final packet
    """

    def __init__(
        self,
        rule_runner: RuleRunner | None = None,
        signal_combiner: SignalCombiner | None = None,
        confidence_scorer: ConfidenceScorer | None = None,
        compressor: PacketCompressor | None = None,
    ):
        self.rule_runner = rule_runner or RuleRunner()
        self.signal_combiner = signal_combiner or SignalCombiner()
        self.confidence_scorer = confidence_scorer or ConfidenceScorer()
        self.compressor = compressor or PacketCompressor()

    def build(self, graph: ValidatedSemanticGraph, generate_summary: bool = True) -> EvidencePacket:
        """Build a complete evidence packet from a validated graph.

        Args:
            graph: The validated semantic graph.
            generate_summary: Whether to auto-generate a summary string.

        Returns:
            A compressed EvidencePacket ready for the LLM.
        """
        # Stage 2: Rule engine — run all rules
        signals = self.rule_runner.run_all(graph)

        # Stage 3: Graph analysis
        execution_analyzer = ExecutionPathAnalyzer(graph)
        execution_evidence = execution_analyzer.analyze()

        impact_analyzer = ImpactAnalyzer(graph)
        impact_evidence = impact_analyzer.analyze()

        coverage_analyzer = CoverageAnalyzer(graph)
        coverage_evidence = coverage_analyzer.analyze()

        architecture_analyzer = ArchitectureAnalyzer(graph)
        architecture_evidence = architecture_analyzer.analyze()

        # Stage 4: Signal combination
        combined_evidence = self.signal_combiner.combine(signals)

        # Stage 7: Confidence scoring
        confidence_summary = self.confidence_scorer.build_confidence_summary(
            signals=signals,
            execution=execution_evidence,
            coverage=coverage_evidence,
            architecture=architecture_evidence,
            combined=combined_evidence,
        )

        # Stage 8: Build packet
        packet = EvidencePacket(
            signals=signals,
            execution_paths=execution_evidence.paths,
            execution_evidence=execution_evidence,
            coverage_evidence=coverage_evidence,
            architecture_evidence=architecture_evidence,
            combined_evidence=combined_evidence,
            confidence_summary=confidence_summary,
        )

        # Stage 9: Compression
        packet = self.compressor.compress(packet)

        # Generate summary
        if generate_summary:
            packet.summary = self._generate_summary(packet, graph)

        return packet

    def _generate_summary(self, packet: EvidencePacket, graph: ValidatedSemanticGraph) -> str:
        """Generate a concise summary of the packet contents."""
        parts = []

        node_count = len(graph.graph.nodes)
        edge_count = len(graph.graph.edges)
        changed_nodes = sum(
            1 for n in graph.graph.nodes.values()
            if n.change_type in ("added", "modified", "deleted")
        )

        parts.append(f"Analysis of {changed_nodes} changed nodes in a graph of {node_count} nodes and {edge_count} edges.")

        if packet.signals:
            parts.append(f"Rules produced {len(packet.signals)} signals.")

        if packet.execution_paths:
            unique_paths = len(set(p.entrypoint for p in packet.execution_paths))
            total_paths = sum(p.count for p in packet.execution_paths)
            parts.append(f"Found {unique_paths} unique execution paths ({total_paths} total).")

        if packet.coverage_evidence:
            untested = (
                len(packet.coverage_evidence.untested_entrypoints)
                + len(packet.coverage_evidence.untested_persistence_paths)
                + len(packet.coverage_evidence.untested_validation)
            )
            if untested > 0:
                parts.append(f"Detected {untested} untested code paths.")

        if packet.combined_evidence:
            parts.append(f"Combined {len(packet.combined_evidence)} higher-level signals.")

        if packet.confidence_summary:
            avg_conf = sum(packet.confidence_summary.values()) / max(len(packet.confidence_summary), 1)
            parts.append(f"Overall confidence: {avg_conf:.2f}.")

        return " ".join(parts)