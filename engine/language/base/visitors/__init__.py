"""Base composite visitor - walks AST once and dispatches to registered handlers.

This enables a single AST traversal per file. All indexing passes
register their handlers and the visitor calls them during traversal.
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from engine.language.base.file_context import FileContext

T = TypeVar("T")


class BaseVisitor(ABC, Generic[T]):
    """Base class for language-specific AST visitors.

    A visitor walks the AST exactly once and dispatches node events
    to registered handler instances.

    To use:
        1. Create a language-specific visitor subclass
        2. Define visit methods for relevant node types
        3. Register collector instances that implement the same interface
        4. Call visit() with a FileContext and builder

    Example:
        class PythonVisitor(BaseVisitor):
            def visit_FunctionDef(self, node, context, builder):
                for collector in self._collectors:
                    collector.visit_FunctionDef(node, context, builder)
    """

    def __init__(self) -> None:
        """Initialize the visitor with an empty collector list."""
        self._collectors: list[Any] = []

    def register(self, collector: Any) -> None:
        """Register a collector to receive node events during traversal.

        Args:
            collector: An object with visit_* methods matching node types
        """
        self._collectors.append(collector)

    @abstractmethod
    def visit(self, context: FileContext[T], builder: dict[str, Any]) -> None:
        """Walk the AST once and dispatch to registered collectors.

        Args:
            context: FileContext with parsed AST
            builder: Mutable builder dict for collected facts
        """
        ...


__all__ = ["BaseVisitor"]