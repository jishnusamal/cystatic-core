"""Coverage models - test coverage information."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Coverage:
    """Test coverage information for execution structures."""
    
    coverage_id: str
    covered_nodes: List[str] = field(default_factory=list)
    uncovered_nodes: List[str] = field(default_factory=list)
    covered_edges: List[str] = field(default_factory=list)
    uncovered_edges: List[str] = field(default_factory=list)
    reachable_tests: List[str] = field(default_factory=list)
    uncovered_paths: List[str] = field(default_factory=list)
    integration_coverage: float = 0.0
    endpoint_coverage: float = 0.0
    model_coverage: float = 0.0
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "coverage_id": self.coverage_id,
            "covered_nodes": self.covered_nodes,
            "uncovered_nodes": self.uncovered_nodes,
            "covered_edges": self.covered_edges,
            "uncovered_edges": self.uncovered_edges,
            "reachable_tests": self.reachable_tests,
            "uncovered_paths": self.uncovered_paths,
            "integration_coverage": self.integration_coverage,
            "endpoint_coverage": self.endpoint_coverage,
            "model_coverage": self.model_coverage,
        }