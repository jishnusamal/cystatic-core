"""IndexCompiler - orchestrates deterministic indexing passes.

The IndexCompiler runs a sequence of language-specific indexing passes
over each file's parsed AST. Each file is parsed exactly once.
Each pass receives FileContext and contributes facts to a FileIndex.

Output: RepositoryIndex (immutable, serializable, cacheable).

This is an embarrassingly parallel stage — each file is independent.
"""

import time
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from language_adapters.base.instrumentation import get_instrumentation
from language_adapters.model.repository_index import (
    CallEntry,
    ConfigEntry,
    EntrypointEntry,
    EventEntry,
    FileIndex,
    ImportEntry,
    PersistenceEntry,
    RawReference,
    RepositoryIndex,
    RepositoryMethodEntry,
    SymbolEntry,
    TestEntry,
    TypeRelationshipEntry,
)


# Type alias for the mutable builder dict used during indexing.
# Keys match FileIndex field names exactly.
_Builder = dict[str, Any]


def _empty_builder(path: str, language: str) -> _Builder:
    """Create an empty builder dict for a file."""
    return {
        "path": path,
        "language": language,
        "symbols": [],
        "imports": [],
        "references": [],
        "calls": [],
        "entrypoints": [],
        "type_relationships": [],
        "persistence_models": [],
        "repository_methods": [],
        "events": [],
        "tests": [],
        "configurations": [],
        "async_entry_points": [],
    }


def _builder_to_file_index(builder: _Builder) -> FileIndex:
    """Convert a builder dict into an immutable FileIndex.

    All list fields are converted to tuples for immutability.
    """
    return FileIndex(
        path=builder["path"],
        language=builder["language"],
        symbols=tuple(builder["symbols"]),
        imports=tuple(builder["imports"]),
        references=tuple(builder["references"]),
        calls=tuple(builder["calls"]),
        entrypoints=tuple(builder["entrypoints"]),
        type_relationships=tuple(builder["type_relationships"]),
        persistence_models=tuple(builder["persistence_models"]),
        repository_methods=tuple(builder["repository_methods"]),
        events=tuple(builder["events"]),
        tests=tuple(builder["tests"]),
        configurations=tuple(builder["configurations"]),
    )


class IndexCompiler:
    """Orchestrates the deterministic indexing pipeline.

    The IndexCompiler runs a sequence of language-specific indexing passes
    over each file's AST. Each file is parsed exactly once by the caller
    and the resulting AST is passed as a FileContext.

    Usage:
        passes = [SymbolPass(), ImportPass(), ...]
        compiler = IndexCompiler(passes)
        index = compiler.compile(file_contexts, language="python")
    """

    def __init__(self, passes: list[BaseIndexPass]) -> None:
        """Initialize the IndexCompiler with a list of indexing passes.

        Args:
            passes: Ordered list of indexing passes to run on each file
        """
        self._passes = list(passes)

    def compile(
        self,
        file_contexts: list[FileContext],
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> RepositoryIndex:
        """Compile a list of FileContexts into a RepositoryIndex.

        Each file is processed exactly once by all passes.
        The resulting FileIndex entries are aggregated into a RepositoryIndex.

        Args:
            file_contexts: List of FileContexts (one per parsed file)
            language: Programming language identifier
            metadata: Additional repository-level metadata

        Returns:
            RepositoryIndex containing all structural facts
        """
        inst = get_instrumentation()
        file_indices: list[FileIndex] = []

        for context in file_contexts:
            builder = _empty_builder(context.path, context.language)
            for pass_instance in self._passes:
                pass_name = type(pass_instance).__name__
                
                start = time.perf_counter()
                try:
                    pass_instance.process(context, builder)
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_pass_time(pass_name, elapsed, context.path)
                    
                    # Count objects emitted
                    for key in ['symbols', 'imports', 'calls', 'entrypoints', 'persistence_models', 
                                'events', 'tests', 'configurations']:
                        if key in builder:
                            inst.increment_counter(pass_name, f"{key}_emitted", len(builder[key]))
            
            file_indices.append(_builder_to_file_index(builder))

        return RepositoryIndex(
            files=tuple(file_indices),
            metadata={
                "language": language,
                **(metadata or {}),
            },
        )

    def compile_with_visitor(
        self,
        file_contexts: list[FileContext],
        language: str,
        visitor: Any,
        metadata: dict[str, Any] | None = None,
    ) -> RepositoryIndex:
        """Compile a list of FileContexts using a composite visitor.

        This method enables single AST traversal per file. The visitor
        walks each AST once and dispatches to all registered indexing passes.

        Args:
            file_contexts: List of FileContexts (one per parsed file)
            language: Programming language identifier
            visitor: Composite visitor that walks AST and dispatches to passes
            metadata: Additional repository-level metadata

        Returns:
            RepositoryIndex containing all structural facts
        """
        inst = get_instrumentation()
        file_indices: list[FileIndex] = []

        for context in file_contexts:
            builder = _empty_builder(context.path, context.language)
            
            # Time the visitor execution
            start = time.perf_counter()
            try:
                visitor.visit(context, builder)
            finally:
                elapsed = time.perf_counter() - start
                inst.record_pass_time("Visitor", elapsed, context.path)
            
            file_indices.append(_builder_to_file_index(builder))

        return RepositoryIndex(
            files=tuple(file_indices),
            metadata={
                "language": language,
                **(metadata or {}),
            },
        )

    @property
    def passes(self) -> list[BaseIndexPass]:
        """Get the list of indexing passes."""
        return list(self._passes)