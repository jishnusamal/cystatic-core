"""Evidence packet — the final compressed output sent to the LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core_engine.models.evidence import (
    Signal,
    ExecutionPath,
    Evidence,
    ExecutionEvidence,
    CoverageEvidence,
    ArchitectureEvidence,
    CombinedEvidence,
)


@dataclass
class EvidencePacket:
    """The final compact packet delivered to the LLM.

    Contains only evidence — no raw graph, no AST, no code, no diff.
    All paths are deduplicated with counts.
    All equivalent evidence is merged.
    Everything references IDs, never names repeatedly.
    """

    summary: str = ""
    signals: List[Signal] = field(default_factory=list)
    execution_paths: List[ExecutionPath] = field(default_factory=list)
    execution_evidence: Optional[ExecutionEvidence] = None
    coverage_evidence: Optional[CoverageEvidence] = None
    architecture_evidence: Optional[ArchitectureEvidence] = None
    combined_evidence: List[CombinedEvidence] = field(default_factory=list)
    confidence_summary: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "signals": [s.to_dict() for s in self.signals],
            "execution_paths": [p.to_dict() for p in self.execution_paths],
            "execution_evidence": self.execution_evidence.to_dict() if self.execution_evidence else None,
            "coverage_evidence": self.coverage_evidence.to_dict() if self.coverage_evidence else None,
            "architecture_evidence": self.architecture_evidence.to_dict() if self.architecture_evidence else None,
            "combined_evidence": [c.to_dict() for c in self.combined_evidence],
            "confidence_summary": self.confidence_summary,
        }

    @property
    def estimated_tokens(self) -> int:
        """Rough estimate of token count for the packet."""
        total = len(self.summary.split())
        for s in self.signals:
            total += len(str(s.to_dict()).split())
        for p in self.execution_paths:
            total += len(p.nodes) + len(p.edges) + 10
        if self.execution_evidence:
            total += 50
        if self.coverage_evidence:
            total += 50
        if self.architecture_evidence:
            total += 50
        for c in self.combined_evidence:
            total += len(str(c.to_dict()).split())
        return total