"""Language adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from schemas import DiffIR
from language_adapters.ir import SemanticGraph


class LanguageAdapter(ABC):
    """Interface every language adapter must implement.

    Each adapter takes a git diff and produces a single SemanticGraph.
    The core engine never knows what an AST is.
    """

    @abstractmethod
    def analyze(self, diff: DiffIR) -> SemanticGraph:
        """Analyze a diff and produce a semantic graph.

        Pipeline:
            1. Load AST(s) for changed files
            2. Compute AST diff (old vs new)
            3. Run all parsers against the diff
            4. Return aggregated SemanticGraph
        """
        ...