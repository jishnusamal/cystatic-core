"""Base rule interface — every rule implements this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from core_engine.models.evidence import Signal
from core_engine.models.semantic_graph import ValidatedSemanticGraph


@dataclass
class RuleResult:
    """Result of executing a rule."""

    rule_name: str
    signals: List[Signal] = field(default_factory=list)

    @property
    def has_signals(self) -> bool:
        return len(self.signals) > 0


class Rule(ABC):
    """Abstract base for all deterministic rules.

    Each rule:
    - Receives the validated semantic graph
    - Produces zero or more signals
    - Never depends on other rules
    - Never invents facts — only reads what's in the graph
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable rule name."""
        ...

    @abstractmethod
    def execute(self, graph: ValidatedSemanticGraph) -> RuleResult:
        """Execute the rule against the validated graph.

        Args:
            graph: The validated semantic graph.

        Returns:
            RuleResult containing any signals produced.
        """
        ...

    def _make_signal(
        self,
        name: str,
        description: str,
        node_ids: List[str] | None = None,
        edge_ids: List[str] | None = None,
        properties: dict | None = None,
    ) -> Signal:
        """Helper to create a signal with this rule's name."""
        return Signal(
            name=name,
            rule_name=self.name,
            description=description,
            node_ids=node_ids or [],
            edge_ids=edge_ids or [],
            properties=properties or {},
            confidence=1.0,
        )