"""Packet compressor — deduplicates, merges, and optimizes the evidence packet."""

from __future__ import annotations

from typing import Dict, List, Set

from core_engine.models.evidence import (
    Signal,
    ExecutionPath,
    CombinedEvidence,
)
from core_engine.models.packet import EvidencePacket


class PacketCompressor:
    """Compresses the evidence packet to be as compact as possible.

    Operations:
    - Remove duplicate paths (merge counts)
    - Remove duplicate signals
    - Merge equivalent evidence
    - Remove repeated symbols/services/nodes
    - Replace repeated paths with count notation
    - Keep packet under ~2K tokens where practical
    """

    def compress(self, packet: EvidencePacket) -> EvidencePacket:
        """Compress the packet in place."""
        packet.signals = self._deduplicate_signals(packet.signals)
        packet.execution_paths = self._deduplicate_paths(packet.execution_paths)
        packet.combined_evidence = self._deduplicate_combined_evidence(packet.combined_evidence)
        return packet

    def _deduplicate_signals(self, signals: List[Signal]) -> List[Signal]:
        """Remove duplicate signals (same name, same nodes)."""
        seen: Set[str] = set()
        deduplicated: List[Signal] = []
        for signal in signals:
            key = f"{signal.name}:{','.join(sorted(signal.node_ids))}"
            if key not in seen:
                seen.add(key)
                deduplicated.append(signal)
        return deduplicated

    def _deduplicate_paths(self, paths: List[ExecutionPath]) -> List[ExecutionPath]:
        """Deduplicate paths with same entrypoint/sink by merging counts."""
        seen: Dict[str, ExecutionPath] = {}
        for path in paths:
            key = f"{path.entrypoint}->{path.sink}"
            if key in seen:
                seen[key].count += path.count
            else:
                seen[key] = path
        return list(seen.values())

    def _deduplicate_combined_evidence(self, evidence_list: List[CombinedEvidence]) -> List[CombinedEvidence]:
        """Remove duplicate combined evidence by description."""
        seen: Set[str] = set()
        deduplicated: List[CombinedEvidence] = []
        for ce in evidence_list:
            if ce.description not in seen:
                seen.add(ce.description)
                deduplicated.append(ce)
        return deduplicated