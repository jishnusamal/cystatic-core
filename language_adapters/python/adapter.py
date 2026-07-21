"""Python language adapter - compiles Python repositories to RepositoryModel.

Architecture:
    Repository → LanguageAdapter → RepositoryIndex → SemanticCompiler → RepositoryModel

    The LanguageAdapter only extracts structural facts (RepositoryIndex).
    The SemanticCompiler performs all semantic reasoning (resolved relationships).
    No semantic work is done in the adapter itself.
"""

import ast
import time
from typing import Any

from language_adapters.base import BaseLanguageAdapter
from language_adapters.base.file_context import FileContext
from language_adapters.base.index_compiler import IndexCompiler
from language_adapters.base.semantic_compiler import SemanticCompiler
from language_adapters.model import RepositoryModel
from language_adapters.model.repository_index import RepositoryIndex
from language_adapters.python.passes import (
    PythonCallIndexPass,
    PythonConfigurationIndexPass,
    PythonEntrypointIndexPass,
    PythonEventIndexPass,
    PythonImportIndexPass,
    PythonPersistenceIndexPass,
    PythonSymbolIndexPass,
    PythonTestIndexPass,
    PythonTypeIndexPass,
)
from language_adapters.python.visitors import PythonVisitor
from runtime.instrumentation.timer import timer


class PythonLanguageAdapter(BaseLanguageAdapter):
    """
    Language adapter for Python repositories.

    Responsibilities:
    1. Parse Python source files into ASTs (once per file)
    2. Run indexing passes to extract structural facts
    3. Compile RepositoryIndex into RepositoryModel via SemanticCompiler

    No semantic reasoning is performed in this adapter.
    All reference resolution, call graph construction, etc. is done
    by the SemanticCompiler.
    """

    def __init__(self):
        """Initialize the adapter with its indexing passes and compilers."""
        # Create indexing passes
        self._passes = [
            PythonSymbolIndexPass(),
            PythonImportIndexPass(),
            PythonCallIndexPass(),
            PythonEntrypointIndexPass(),
            PythonTypeIndexPass(),
            PythonPersistenceIndexPass(),
            PythonEventIndexPass(),
            PythonTestIndexPass(),
            PythonConfigurationIndexPass(),
        ]
        self._index_compiler = IndexCompiler(self._passes)
        self._semantic_compiler = SemanticCompiler()
        
        # Create composite visitor for single AST traversal
        self._visitor = PythonVisitor()
        for pass_instance in self._passes:
            self._visitor.register(pass_instance)

    def get_language(self) -> str:
        """Get the language name this adapter handles."""
        return "python"

    def get_compiler_passes(self) -> list[str]:
        """Get the names of indexing passes this adapter uses.

        Returns the same pass names as the previous extractor-based
        architecture for backward compatibility.
        """
        return [
            "symbol_collection",
            "reference_resolution",
            "call_graph",
            "endpoint_discovery",
            "type_relationships",
            "async_entry_points",
            "persistence_models",
            "repository_methods",
            "event_constructs",
            "test_definitions",
            "configuration_references",
        ]

    def compile(self, repository_input: dict[str, Any]) -> RepositoryModel:
        """Compile a Python repository into a RepositoryModel.

        Args:
            repository_input: Repository snapshot containing:
                - files: dict[file_path, file_content]
                - language: str (should be "python")

        Returns:
            RepositoryModel: Language-independent repository representation
        """
        files = repository_input.get('files', {})
        language = repository_input.get('language', self.get_language())

        # Step 1: Build RepositoryIndex (structural facts only)
        index = self._build_index(files, language)

        # Step 2: Compile RepositoryIndex into RepositoryModel (semantic)
        return self._semantic_compiler.compile(index, language)

    def build_index(self, repository_input: dict[str, Any]) -> RepositoryIndex:
        """Build a RepositoryIndex from repository data.

        This allows downstream consumers to access the raw index
        without triggering semantic compilation.

        Args:
            repository_input: Repository snapshot with 'files' key

        Returns:
            RepositoryIndex containing only structural facts
        """
        files = repository_input.get('files', {})
        language = repository_input.get('language', self.get_language())
        return self._build_index(files, language)

    def _build_index(self, files: dict[str, str], language: str) -> RepositoryIndex:
        """Build a RepositoryIndex from raw source files.

        Each file is parsed exactly once. The composite visitor walks
        the AST once and dispatches to all indexing passes.

        Args:
            files: Dictionary mapping file paths to file contents
            language: Programming language identifier

        Returns:
            RepositoryIndex containing structural facts
        """
        file_contexts: list[FileContext[ast.AST]] = []
        files_skipped = 0
        files_failed = 0
        parse_times: list[float] = []
        slow_files: list[tuple[str, float]] = []

        # Parse all files
        for file_path, content in files.items():
            if not file_path.endswith('.py'):
                files_skipped += 1
                continue

            try:
                start_time = time.perf_counter()
                tree = ast.parse(content, filename=file_path)
                parse_time = time.perf_counter() - start_time
                parse_times.append(parse_time)
                
                # Log slow parses (>100ms)
                if parse_time > 0.1:
                    slow_files.append((file_path, parse_time))
                
                context = FileContext(
                    path=file_path,
                    source=content,
                    ast=tree,
                    language=language,
                )
                file_contexts.append(context)
            except SyntaxError:
                files_failed += 1
                continue

        # Log parsing statistics
        total_parse_time = sum(parse_times)
        avg_parse_time = total_parse_time / len(parse_times) if parse_times else 0
        
        print(f"[adapter] Python Files: {len(files)} total, {len(file_contexts)} parsed, {files_skipped} skipped, {files_failed} failed")
        print(f"[adapter] Total AST Parse Time: {total_parse_time:.3f}s")
        print(f"[adapter] Average Parse Time: {avg_parse_time * 1000:.2f}ms/file")
        
        if slow_files:
            print(f"[adapter] Slow Parses (>100ms):")
            for file_path, parse_time in sorted(slow_files, key=lambda x: x[1], reverse=True)[:10]:
                print(f"[adapter]   {file_path}: {parse_time * 1000:.2f}ms")

        # Use composite visitor for single AST traversal per file
        with timer.timed("Visitor", metadata={"files": len(file_contexts)}):
            index = self._index_compiler.compile_with_visitor(file_contexts, language, self._visitor)
        
        # Log indexing statistics
        print(f"[adapter] Symbols Indexed: {len(index.all_symbols)}")
        print(f"[adapter] Imports Indexed: {len(index.all_imports)}")
        print(f"[adapter] Calls Indexed: {len(index.all_calls)}")
        print(f"[adapter] Entrypoints Indexed: {len(index.all_entrypoints)}")
        print(f"[adapter] Persistence Models: {len(index.all_persistence_models)}")
        print(f"[adapter] Events: {len(index.all_events)}")
        print(f"[adapter] Tests: {len(index.all_tests)}")
        print(f"[adapter] Configurations: {len(index.all_configurations)}")
        
        # Print visitor instrumentation
        from language_adapters.base.instrumentation import get_instrumentation
        inst = get_instrumentation()
        inst.print_pass_summary()
        inst.print_method_summary()
        inst.print_top_operations(n=50)
        inst.print_hotspot_analysis()
        
        # Return RepositoryIndex (semantic compilation happens in compile())
        return index
