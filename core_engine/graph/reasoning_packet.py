"""ReasoningPacket - final output of the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ReasoningPacket:
    """Final output of the pipeline - what the LLM sees.
    
    This is a compact, high-signal representation instead of thousands
    of raw graph nodes and edges.
    """
    
    summary: str = ""
    
    changed_areas: List[str] = field(default_factory=list)
    semantic_changes: List[str] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    migrations: List[str] = field(default_factory=list)
    validations: List[str] = field(default_factory=list)
    persistence: List[str] = field(default_factory=list)
    transactions: List[str] = field(default_factory=list)
    queries: List[str] = field(default_factory=list)
    external_calls: List[str] = field(default_factory=list)
    tests: List[Dict[str, Any]] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "summary": self.summary,
            "changed_areas": self.changed_areas,
            "semantic_changes": self.semantic_changes,
            "relationships": self.relationships,
            "migrations": self.migrations,
            "validations": self.validations,
            "persistence": self.persistence,
            "transactions": self.transactions,
            "queries": self.queries,
            "external_calls": self.external_calls,
            "tests": self.tests,
            "unresolved": self.unresolved,
        }