"""TypeScript language adapter - compiles TypeScript repositories to RepositoryModel.

Architecture:
    Repository → LanguageAdapter → RepositoryIndex → SemanticCompiler → RepositoryModel

    The LanguageAdapter only extracts structural facts (RepositoryIndex).
    The SemanticCompiler performs all semantic reasoning (resolved relationships).
    No semantic work is done in the adapter itself.
"""

import time
from typing import Any

from core.logging import timer
from engine.language.base import BaseLanguageAdapter
from engine.language.base.file_context import FileContext
from engine.language.base.index_compiler import IndexCompiler
from engine.language.base.semantic_compiler import SemanticCompiler
from engine.language.typescript.parser import TypeScriptParser
from engine.language.typescript.passes import (
    TypeScriptCallIndexPass,
    TypeScriptConfigurationIndexPass,
    TypeScriptEntrypointIndexPass,
    TypeScriptEventIndexPass,
    TypeScriptImportIndexPass,
    TypeScriptPersistenceIndexPass,
    TypeScriptSymbolIndexPass,
    TypeScriptTestIndexPass,
    TypeScriptTypeIndexPass,
)
from engine.language.typescript.visitors import TypeScriptVisitor
from engine.repository.model import RepositoryModel
from engine.repository.model.repository_index import FileIndex, RepositoryIndex


class TypeScriptLanguageAdapter(BaseLanguageAdapter):
    """
    Language adapter for TypeScript repositories.

    Responsibilities:
    1. Parse TypeScript source files into Tree-sitter Trees (once per file)
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
            TypeScriptSymbolIndexPass(),
            TypeScriptImportIndexPass(),
            TypeScriptCallIndexPass(),
            TypeScriptEntrypointIndexPass(),
            TypeScriptTypeIndexPass(),
            TypeScriptPersistenceIndexPass(),
            TypeScriptEventIndexPass(),
            TypeScriptTestIndexPass(),
            TypeScriptConfigurationIndexPass(),
        ]
        self._index_compiler = IndexCompiler(self._passes)
        self._semantic_compiler = SemanticCompiler()
        self._parser = TypeScriptParser()

        # Create composite visitor for single AST traversal
        self._visitor = TypeScriptVisitor()
        for pass_instance in self._passes:
            self._visitor.register(pass_instance)

    def get_language(self) -> str:
        """Get the language name this adapter handles."""
        return "typescript"

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
        """Compile a TypeScript repository into a RepositoryModel.

        Args:
            repository_input: Repository snapshot containing:
                - files: dict[file_path, file_content]
                - language: str (should be "typescript")

        Returns:
            RepositoryModel: Language-independent repository representation
        """
        files = repository_input.get("files", {})
        language = repository_input.get("language", self.get_language())

        # Step 1: Build RepositoryIndex (structural facts only)
        index = self._build_index(files, language)

        # Step 2: Compile RepositoryIndex into RepositoryModel (semantic)
        from typing import cast

        return cast(RepositoryModel, self._semantic_compiler.compile(index, language))

    def build_index(self, repository_input: dict[str, Any]) -> RepositoryIndex:
        """Build a RepositoryIndex from repository data.

        This allows downstream consumers to access the raw index
        without triggering semantic compilation.

        Args:
            repository_input: Repository snapshot with 'files' key

        Returns:
            RepositoryIndex containing only structural facts
        """
        files = repository_input.get("files", {})
        language = repository_input.get("language", self.get_language())
        return self._build_index(files, language)

    def _build_index(self, files: dict[str, str], language: str) -> RepositoryIndex:
        """Build a RepositoryIndex from raw source files.

        Each file is parsed and indexed one by one to avoid keeping
        all trees in memory simultaneously.

        Args:
            files: Dictionary mapping file paths to file contents
            language: Programming language identifier

        Returns:
            RepositoryIndex containing structural facts
        """
        ts_extensions = (".ts", ".tsx", ".mts", ".cts")
        ts_files = [f for f in files if f.endswith(ts_extensions)]
        num_ts_files = len(ts_files)
        files_skipped = len(files) - num_ts_files
        files_failed = 0
        files_parsed = 0
        parse_times: list[float] = []
        slow_files: list[tuple[str, float]] = []

        def generate_contexts():
            nonlocal files_failed, files_parsed
            for file_path in ts_files:
                content = files.get(file_path)
                if content is None:
                    continue

                try:
                    start_time = time.perf_counter()
                    tree = self._parser.parse(content, file_path)
                    parse_time = time.perf_counter() - start_time
                    parse_times.append(parse_time)

                    if parse_time > 0.1:
                        slow_files.append((file_path, parse_time))

                    context = FileContext(
                        path=file_path,
                        source=content,
                        ast=tree,
                        language=language,
                    )
                    files_parsed += 1
                    yield context
                except Exception:  # noqa: BLE001 -- isolate per-file parse/index failures during indexing
                    files_failed += 1
                    continue

        from core.profile import get_current_profiler

        profiler = get_current_profiler()

        # Use composite visitor for single AST traversal per file
        with timer.timed("Visitor", metadata={"files": num_ts_files}):
            index = self._index_compiler.compile_with_visitor(
                generate_contexts(), language, self._visitor
            )

        # Log parsing & indexing statistics (after generator is exhausted)
        total_parse_time = sum(parse_times)
        avg_parse_time = total_parse_time / len(parse_times) if parse_times else 0

        if profiler:
            profiler.log_memory("After parsing and symbol extraction")
            profiler.log_memory("After endpoint extraction")
            profiler.log_memory("After dependency/relationship extraction")

        from core.logging import pipeline_logger

        def log(msg: str) -> None:
            pipeline_logger.log_pipeline(msg, to_terminal=False)

        log(
            f"[adapter] TypeScript Files: {len(files)} total, {files_parsed} parsed, {files_skipped} skipped, {files_failed} failed"
        )
        log(f"[adapter] Total AST Parse Time: {total_parse_time:.3f}s")
        log(f"[adapter] Average Parse Time: {avg_parse_time * 1000:.2f}ms/file")

        if slow_files:
            log("[adapter] Slow Parses (>100ms):")
            for file_path, parse_time in sorted(
                slow_files, key=lambda x: x[1], reverse=True
            )[:10]:
                log(f"[adapter]   {file_path}: {parse_time * 1000:.2f}ms")

        # Log indexing statistics
        log(f"[adapter] Symbols Indexed: {len(index.all_symbols)}")
        log(f"[adapter] Imports Indexed: {len(index.all_imports)}")
        log(f"[adapter] Calls Indexed: {len(index.all_calls)}")
        log(f"[adapter] Entrypoints Indexed: {len(index.all_entrypoints)}")
        log(f"[adapter] Persistence Models: {len(index.all_persistence_models)}")
        log(f"[adapter] Events: {len(index.all_events)}")
        log(f"[adapter] Tests: {len(index.all_tests)}")
        log(f"[adapter] Configurations: {len(index.all_configurations)}")

        # Print visitor instrumentation
        from engine.language.base.instrumentation import get_instrumentation

        inst = get_instrumentation()
        inst.print_pass_summary()
        inst.print_method_summary()
        inst.print_top_operations(n=50)
        inst.print_hotspot_analysis()

        # Print concise profile summary for terminal output in profile mode
        inst.print_profile_summary()

        return index

    def _index_single_file(
        self, file_path: str, content: str, language: str
    ) -> FileIndex:
        """Parse and run indexing passes on a single source file."""
        ts_extensions = (".ts", ".tsx", ".mts", ".cts")
        if not file_path.endswith(ts_extensions):
            from engine.repository.model.repository_index import FileIndex

            return FileIndex(path=file_path, language=language)

        try:
            tree = self._parser.parse(content, file_path)
            context = FileContext(
                path=file_path,
                source=content,
                ast=tree,
                language=language,
            )
            repo_index = self._index_compiler.compile_with_visitor(
                [context], language, self._visitor
            )
            return repo_index.files[0]
        except Exception:  # noqa: BLE001 -- isolate per-file parse/index failures during indexing
            from engine.repository.model.repository_index import FileIndex

            return FileIndex(path=file_path, language=language)
