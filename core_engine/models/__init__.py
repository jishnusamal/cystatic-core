"""Core Engine data models - immutable contracts."""

from core_engine.models.knowledge_model import KnowledgeModel
from core_engine.models.evidence import (
    Evidence,
    ExecutionEvidence,
    CoverageEvidence,
    ArchitectureEvidence,
    CombinedEvidence,
    ExecutionPath,
    EvidenceCategory,
)
from core_engine.models.signal import Signal, SignalCategory
from core_engine.models.execution import ExecutionUnit
from core_engine.models.interaction import InteractionCluster
from core_engine.models.propagation import PropagationPath
from core_engine.models.coverage import Coverage
from core_engine.models.review_context import ReviewContext
from core_engine.models.compiler_pass import CompilerPass, PassResult

__all__ = [
    "KnowledgeModel",
    "Evidence",
    "ExecutionEvidence",
    "CoverageEvidence",
    "ArchitectureEvidence",
    "CombinedEvidence",
    "ExecutionPath",
    "EvidenceCategory",
    "Signal",
    "SignalCategory",
    "ExecutionUnit",
    "InteractionCluster",
    "PropagationPath",
    "Coverage",
    "ReviewContext",
    "CompilerPass",
    "PassResult",
]