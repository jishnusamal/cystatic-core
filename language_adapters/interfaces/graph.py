"""Graph builder interface — every parser implements this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from language_adapters.ir import SemanticGraph


class GraphBuilder(ABC):
    """Interface for graph-building components.

    Every parser in the pipeline implements this interface.
    Each parser receives a graph and mutates it — no parser returns "signals".
    """

    @abstractmethod
    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        """Mutate the graph with semantic facts extracted from context.

        Args:
            graph: The semantic graph being built (mutated in place).
            context: Parser-specific context (AST nodes, diff info, etc.).

        Returns:
            The same graph instance (for chaining).
        """
        ...