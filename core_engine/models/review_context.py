"""ReviewContext - LLM reasoning package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ReviewContext:
    """Context package for LLM reasoning.
    
    Contains all analyzed information about the change,
    but no conclusions - those are left to the LLM.
    """
    
    context_id: str
    graph_id: str
    commit_hash: str
    
    # Changed execution units
    changed_execution_units: List[str] = field(default_factory=list)
    
    # Interaction analysis
    interaction_clusters: List[str] = field(default_factory=list)
    
    # Propagation paths
    propagation_paths: List[str] = field(default_factory=list)
    
    # Evidence
    evidence: List[str] = field(default_factory=list)
    
    # Signals
    signals: List[str] = field(default_factory=list)
    
    # Coverage
    coverage: Optional[str] = None
    
    # Statistics
    statistics: Dict[str, Any] = field(default_factory=dict)
    
    # Raw data for LLM to analyze
    raw_facts: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "context_id": self.context_id,
            "graph_id": self.graph_id,
            "commit_hash": self.commit_hash,
            "changed_execution_units": self.changed_execution_units,
            "interaction_clusters": self.interaction_clusters,
            "propagation_paths": self.propagation_paths,
            "evidence": self.evidence,
            "signals": self.signals,
            "coverage": self.coverage,
            "statistics": self.statistics,
            "raw_facts": self.raw_facts,
        }