"""Heuristic refactor risk from graph metrics."""

from __future__ import annotations

from dataclasses import dataclass

from core_engine.dependency_graph import DependencyGraph
from core_engine.impact_calculator import ImpactCalculator


@dataclass
class RefactorRisk:
    """Risk assessment for editing ``node``."""

    node: str
    affected_nodes: int
    impact_score: float
    risk_level: str  # "low" | "medium" | "high"


class RefactorRiskEstimator:
    """Combines impact with simple thresholds."""

    def __init__(self, graph: DependencyGraph) -> None:
        self._calc = ImpactCalculator(graph)

    def estimate(self, node: str) -> RefactorRisk:
        affected = self._calc.affected_count(node)
        score = self._calc.impact_score(node)
        if score < 0.15:
            level = "low"
        elif score < 0.4:
            level = "medium"
        else:
            level = "high"
        return RefactorRisk(
            node=node,
            affected_nodes=affected,
            impact_score=score,
            risk_level=level,
        )
