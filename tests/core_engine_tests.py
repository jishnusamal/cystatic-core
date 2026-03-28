"""Tests for core_engine."""

from core_engine.dependency_graph import DependencyGraph
from core_engine.impact_calculator import ImpactCalculator
from core_engine.refactor_risk import RefactorRiskEstimator


def test_blast_radius_follows_reverse_edges() -> None:
    g = DependencyGraph()
    g.add_edge("b.py", "a.py")
    g.add_edge("c.py", "b.py")
    assert g.blast_radius("a.py") == {"b.py", "c.py"}


def test_impact_and_risk() -> None:
    g = DependencyGraph()
    g.add_edge("b.py", "a.py")
    calc = ImpactCalculator(g)
    assert calc.affected_count("a.py") == 1
    est = RefactorRiskEstimator(g)
    r = est.estimate("a.py")
    assert r.node == "a.py"
    assert r.risk_level in ("low", "medium", "high")
