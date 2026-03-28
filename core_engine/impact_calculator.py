"""Impact scoring from dependency structure."""

from __future__ import annotations

from dataclasses import dataclass

from core_engine.dependency_graph import DependencyGraph


@dataclass
class ImpactCalculator:
    """Scores impact of changes to a node using the dependency graph."""

    graph: DependencyGraph

    def affected_count(self, changed: str) -> int:
        """Number of distinct nodes affected (excluding the changed node)."""
        return len(self.graph.blast_radius(changed))

    def impact_score(self, changed: str) -> float:
        """Normalized score in ``[0, 1]`` (higher = wider blast radius)."""
        n = len(self.graph.forward) or 1
        return min(1.0, self.affected_count(changed) / n)
