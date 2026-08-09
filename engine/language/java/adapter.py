"""Java language adapter - compiles Java repositories to RepositoryModel.

Architecture:
    Repository → LanguageAdapter → RepositoryIndex → SemanticCompiler → RepositoryModel

    The LanguageAdapter only extracts structural facts (RepositoryIndex).
    The SemanticCompiler performs all semantic reasoning (resolved relationships).
    No semantic work is done in the adapter itself.

Note: This is a simplified implementation using regex-based parsing.
A production version would use a proper Java parser like JavaParser.
"""

from typing import Any

from engine.language.base import BaseLanguageAdapter
from engine.language.base.file_context import FileContext
from engine.language.base.index_compiler import IndexCompiler
from engine.language.base.semantic_compiler import SemanticCompiler
from engine.language.java.parser import JavaParser
from engine.repository.model import RepositoryModel
from engine.repository.model.repository_index import RepositoryIndex
from engine.language.java.passes import (
    JavaSymbolIndexPass,
    JavaImportIndexPass,
    JavaCallIndexPass,
    JavaEntrypointIndexPass,
    JavaTypeIndexPass,
    JavaPersistenceIndexPass,
    JavaEventIndexPass,
    JavaTestIndexPass,
    JavaConfigurationIndexPass,
)


class JavaLanguageAdapter(BaseLanguageAdapter):
    """
    Language adapter for Java repositories.

    Responsibilities:
    1. Parse Java source files into line lists (once per file)
    2. Run indexing passes to extract structural facts
    3. Compile RepositoryIndex into RepositoryModel via SemanticCompiler

    No semantic reasoning is performed in this adapter.
    All reference resolution, call graph construction, etc. is done
    by the SemanticCompiler.
    """

    def __init__(self):
        """Initialize the adapter with its indexing passes and compilers."""
        self._parser = JavaParser()
        self._index_compiler = IndexCompiler([
            JavaSymbolIndexPass(),
            JavaImportIndexPass(),
            JavaCallIndexPass(),
            JavaEntrypointIndexPass(),
            JavaTypeIndexPass(),
            JavaPersistenceIndexPass(),
            JavaEventIndexPass(),
            JavaTestIndexPass(),
            JavaConfigurationIndexPass(),
        ])
        self._semantic_compiler = SemanticCompiler()

    def get_language(self) -> str:
        """Get the language name this adapter handles."""
        return "java"

    def get_compiler_passes(self) -> list[str]:
        """Get the names of compiler passes this adapter uses.

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
        """
        Compile a Java repository into a RepositoryModel.

        Args:
            repository_input: Repository snapshot containing:
                - files: dict[file_path, file_content]
                - language: str (should be "java")

        Returns:
            RepositoryModel: Language-independent repository representation
        """
        files = repository_input.get('files', {})
        language = repository_input.get('language', self.get_language())

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
        files = repository_input.get('files', {})
        language = repository_input.get('language', self.get_language())
        return self._build_index(files, language)

    def _build_index(self, files: dict[str, str], language: str) -> RepositoryIndex:
        """Build a RepositoryIndex from raw source files.

        Each file is parsed exactly once. All indexing passes
        share the same parsed representation.

        Args:
            files: Dictionary mapping file paths to file contents
            language: Programming language identifier

        Returns:
            RepositoryIndex containing structural facts
        """
        file_contexts: list[FileContext[list[str]]] = []

        for file_path, content in files.items():
            if not file_path.endswith('.java'):
                continue

            try:
                lines = self._parser.parse(content, file_path)
            except Exception:
                continue

            context = FileContext(
                path=file_path,
                source=content,
                ast=lines,
                language=language,
            )
            file_contexts.append(context)

        return self._index_compiler.compile(file_contexts, language)

    def _index_single_file(self, file_path: str, content: str, language: str) -> Any:
        """Parse and run indexing passes on a single source file."""
        if not file_path.endswith('.java'):
            from engine.repository.model.repository_index import FileIndex
            return FileIndex(path=file_path, language=language)
            
        try:
            lines = self._parser.parse(content, file_path)
            context = FileContext(
                path=file_path,
                source=content,
                ast=lines,
                language=language,
            )
            repo_index = self._index_compiler.compile([context], language)
            return repo_index.files[0]
        except Exception:
            from engine.repository.model.repository_index import FileIndex
            return FileIndex(path=file_path, language=language)
