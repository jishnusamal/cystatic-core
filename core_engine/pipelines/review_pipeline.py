"""Review pipeline — orchestrates the full core engine workflow end-to-end."""

from __future__ import annotations

from typing import Dict, List, Optional

from language_adapters.ir.semantic_graph import SemanticGraph

from core_engine.models.semantic_graph import ValidatedSemanticGraph
from core_engine.models.packet import EvidencePacket
from core_engine.packet.packet_builder import PacketBuilder


class ReviewPipeline:
    """End-to-end pipeline for PR review analysis.

    Pipeline:
    1. Load SemanticGraph (from adapter)
    2. Validate graph structure
    3. Run rule engine (all rules)
    4. Run graph analysis (execution paths, impact, coverage, architecture)
    5. Combine signals into higher-level evidence
    6. Compute confidence scores
    7. Compress packet
    8. Output EvidencePacket for LLM

    The pipeline is completely language-agnostic.
    It never parses source code or understands language syntax.
    """

    def __init__(self, packet_builder: PacketBuilder | None = None):
        self.packet_builder = packet_builder or PacketBuilder()

    def run(self, graph: SemanticGraph) -> EvidencePacket:
        """Run the full review pipeline on a semantic graph.

        Args:
            graph: The raw semantic graph from a language adapter.

        Returns:
            A compressed EvidencePacket ready for the LLM.

        Raises:
            ValueError: If the graph fails validation.
        """
        # Stage 1: Validate
        validated = ValidatedSemanticGraph.validate(graph)

        if not validated.is_valid:
            raise ValueError(
                f"Graph validation failed with {len(validated.errors)} errors:\n"
                + "\n".join(validated.errors)
            )

        # Stages 2-9: Build packet
        packet = self.packet_builder.build(validated)

        return packet

    def run_with_warnings(self, graph: SemanticGraph) -> tuple[EvidencePacket, List[str]]:
        """Run pipeline but return warnings instead of raising on validation errors.

        Args:
            graph: The raw semantic graph from a language adapter.

        Returns:
            Tuple of (EvidencePacket, warnings list).
            If validation fails, returns an empty packet with warnings.
        """
        validated = ValidatedSemanticGraph.validate(graph)

        if not validated.is_valid:
            empty_packet = EvidencePacket(
                summary="Graph validation failed — no analysis possible.",
            )
            return empty_packet, validated.errors

        packet = self.packet_builder.build(validated)
        return packet, validated.warnings