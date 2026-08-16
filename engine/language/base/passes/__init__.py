"""Base index pass abstraction for the deterministic indexing pipeline."""

from abc import ABC, abstractmethod
from typing import Any

from engine.language.base.file_context import FileContext
from engine.repository.model.repository_index import FileIndex


class BaseIndexPass(ABC):
    """Base class for all indexing passes.

    Every pass has exactly one responsibility.
    Every pass is independent and receives FileContext.
    No pass should open files or parse ASTs.

    Each pass mutates the in-progress FileIndex builder dict
    by adding its extracted facts.
    """

    @abstractmethod
    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Process a file context and add facts to the builder.

        Args:
            context: FileContext with parsed AST and source info
            builder: Mutable dict that will become a FileIndex.
                     Passes should append their facts to the appropriate keys.
        """
        ...


__all__ = ["BaseIndexPass"]
