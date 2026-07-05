"""Core engine — transforms semantic graphs into structured evidence for the LLM.

The core engine is completely language-agnostic. It never parses source code
or understands language syntax. It only consumes the standardized semantic
graph produced by language adapters.

Pipeline:
    SemanticGraph → Validate → Rules → Analysis → Combine → Confidence → Compress → EvidencePacket
"""

from core_engine.models.semantic_graph import ValidatedSemanticGraph
from core_engine.models.evidence import (
    Signal,
    Evidence,
    ExecutionEvidence,
    CoverageEvidence,
    ArchitectureEvidence,
    CombinedEvidence,
    ExecutionPath,
)
from core_engine.models.packet import EvidencePacket
from core_engine.pipelines.review_pipeline import ReviewPipeline
from core_engine.packet.packet_builder import PacketBuilder
from core_engine.inference.rule_runner import RuleRunner
from core_engine.inference.signal_combiner import SignalCombiner
from core_engine.inference.confidence import ConfidenceScorer
from core_engine.rules.coverage import CoverageRule

__all__ = [
    "ValidatedSemanticGraph",
    "Signal",
    "Evidence",
    "ExecutionEvidence",
    "CoverageEvidence",
    "ArchitectureEvidence",
    "CombinedEvidence",
    "ExecutionPath",
    "EvidencePacket",
    "ReviewPipeline",
    "PacketBuilder",
    "RuleRunner",
    "SignalCombiner",
    "ConfidenceScorer",
]