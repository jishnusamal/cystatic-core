"""Rule runner — loads and executes all rules, merging results."""

from __future__ import annotations

from typing import Dict, List, Type

from core_engine.models.semantic_graph import ValidatedSemanticGraph
from core_engine.models.evidence import Signal
from core_engine.rules.base import Rule, RuleResult
from core_engine.rules import (
    ValidationRule,
    PersistenceRule,
    QueryRule,
    TransactionRule,
    MigrationRule,
    APIExposureRule,
    EventRule,
    CacheRule,
    AuthRule,
    ExternalDependencyRule,
    CrossDomainRule,
    CoverageRule,
)


class RuleRunner:
    """Loads and executes all rules, merging results into a single signal set.

    Rules are completely independent — no rule knows another exists.
    The runner simply loads every rule, executes them, and merges the results.
    """

    def __init__(self, rules: List[Rule] | None = None):
        self._rules = rules or self._default_rules()

    @staticmethod
    def _default_rules() -> List[Rule]:
        """Create the default set of rules."""
        return [
            ValidationRule(),
            PersistenceRule(),
            QueryRule(),
            TransactionRule(),
            MigrationRule(),
            APIExposureRule(),
            EventRule(),
            CacheRule(),
            AuthRule(),
            ExternalDependencyRule(),
            CrossDomainRule(),
            CoverageRule(),
        ]

    def register_rule(self, rule: Rule) -> None:
        """Register an additional rule."""
        self._rules.append(rule)

    def run_all(self, graph: ValidatedSemanticGraph) -> List[Signal]:
        """Execute all rules against the graph and merge signals.

        Args:
            graph: The validated semantic graph.

        Returns:
            Merged list of all signals from all rules.
        """
        all_signals: List[Signal] = []
        results: List[RuleResult] = []

        for rule in self._rules:
            result = rule.execute(graph)
            results.append(result)
            all_signals.extend(result.signals)

        return all_signals

    def run_all_with_results(self, graph: ValidatedSemanticGraph) -> List[RuleResult]:
        """Execute all rules and return individual results (for debugging)."""
        results: List[RuleResult] = []
        for rule in self._rules:
            result = rule.execute(graph)
            results.append(result)
        return results

    @property
    def rules(self) -> List[Rule]:
        return list(self._rules)