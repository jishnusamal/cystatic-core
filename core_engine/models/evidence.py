"""Evidence models - traceable proof structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvidenceCategory(Enum):
    """Categories of evidence."""
    EXECUTION = "execution"
    COVERAGE = "coverage"
    ARCHITECTURE = "architecture"
    PROPAGATION = "propagation"
    INTERACTION = "interaction"
    SURFACE = "surface"
    COMBINED = "combined"


@dataclass(frozen=True)
class ExecutionPath:
    """A proven execution path through the system."""
    
    path_id: str
    entrypoint: str  # Node ID
    sink: str  # Node ID
    nodes: List[str]  # Ordered list of node IDs
    edges: List[str]  # Ordered list of edge IDs
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "path_id": self.path_id,
            "entrypoint": self.entrypoint,
            "sink": self.sink,
            "nodes": self.nodes,
            "edges": self.edges,
        }


@dataclass(frozen=True)
class Evidence:
    """Base evidence - a claim with proof."""
    
    evidence_id: str
    category: EvidenceCategory
    description: str
    claim: str
    proof: List[str]  # Node/edge IDs that prove this claim
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "evidence_id": self.evidence_id,
            "category": self.category.value,
            "description": self.description,
            "claim": self.claim,
            "proof": self.proof,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ExecutionEvidence(Evidence):
    """Evidence about executable structures."""
    
    paths: List[ExecutionPath] = field(default_factory=list)
    entrypoints: List[str] = field(default_factory=list)
    sinks: List[str] = field(default_factory=list)
    
    def __init__(self, *args, **kwargs):
        """Initialize with category EXECUTION."""
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "category", EvidenceCategory.EXECUTION)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        base = super().to_dict()
        base["paths"] = [p.to_dict() for p in self.paths]
        base["entrypoints"] = self.entrypoints
        base["sinks"] = self.sinks
        return base


@dataclass(frozen=True)
class CoverageEvidence(Evidence):
    """Evidence about test coverage."""
    
    covered_nodes: List[str] = field(default_factory=list)
    uncovered_nodes: List[str] = field(default_factory=list)
    covered_edges: List[str] = field(default_factory=list)
    uncovered_edges: List[str] = field(default_factory=list)
    reachable_tests: List[str] = field(default_factory=list)
    
    def __init__(self, *args, **kwargs):
        """Initialize with category COVERAGE."""
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "category", EvidenceCategory.COVERAGE)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        base = super().to_dict()
        base["covered_nodes"] = self.covered_nodes
        base["uncovered_nodes"] = self.uncovered_nodes
        base["covered_edges"] = self.covered_edges
        base["uncovered_edges"] = self.uncovered_edges
        base["reachable_tests"] = self.reachable_tests
        return base


@dataclass(frozen=True)
class ArchitectureEvidence(Evidence):
    """Evidence about architectural structures."""
    
    new_apis: List[str] = field(default_factory=list)
    new_database_access: List[str] = field(default_factory=list)
    new_external_calls: List[str] = field(default_factory=list)
    new_events: List[str] = field(default_factory=list)
    new_schemas: List[str] = field(default_factory=list)
    
    def __init__(self, *args, **kwargs):
        """Initialize with category ARCHITECTURE."""
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "category", EvidenceCategory.ARCHITECTURE)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        base = super().to_dict()
        base["new_apis"] = self.new_apis
        base["new_database_access"] = self.new_database_access
        base["new_external_calls"] = self.new_external_calls
        base["new_events"] = self.new_events
        base["new_schemas"] = self.new_schemas
        return base


@dataclass(frozen=True)
class CombinedEvidence(Evidence):
    """Evidence combined from multiple sources."""
    
    source_signals: List[str] = field(default_factory=list)  # Signal IDs
    source_evidence: List[str] = field(default_factory=list)  # Evidence IDs
    
    def __init__(self, *args, **kwargs):
        """Initialize with category COMBINED."""
        super().__init__(*args, **kwargs)
        object.__setattr__(self, "category", EvidenceCategory.COMBINED)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        base = super().to_dict()
        base["source_signals"] = self.source_signals
        base["source_evidence"] = self.source_evidence
        return base