"""FileContext - reusable per-file context for indexing passes.

Every indexing pass receives a FileContext containing the parsed AST,
source path, source code, language, and metadata. No pass should
reopen files or reparse ASTs.
"""

from typing import Any, Generic, TypeVar

T = TypeVar("T")


class FileContext(Generic[T]):
    """Reusable per-file context for indexing passes.

    Created once per file during indexing and passed to every indexing pass.
    No pass should open files or parse ASTs — that work is done once here.

    Attributes:
        path: Source file path relative to repository root
        source: Raw source code content
        ast: Language-native parsed syntax tree
        language: Programming language identifier
        metadata: Additional file-level key-value pairs
    """

    __slots__ = ("path", "source", "ast", "language", "metadata")

    def __init__(
        self,
        path: str,
        source: str,
        ast: T,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize file context.

        Args:
            path: Source file path relative to repository root
            source: Raw source code content
            ast: Language-native parsed syntax tree
            language: Programming language identifier
            metadata: Additional file-level key-value pairs
        """
        self.path = path
        self.source = source
        self.ast = ast
        self.language = language
        self.metadata = metadata or {}