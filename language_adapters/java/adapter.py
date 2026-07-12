"""Java language adapter - compiles Java repositories to RepositoryModel."""

from typing import Any

from language_adapters.base import BaseLanguageAdapter, ModelCompiler
from language_adapters.model import RepositoryModel
from language_adapters.java.extractors import (
    JavaSymbolExtractor,
    JavaImportExtractor,
    JavaCallExtractor,
    JavaEntrypointExtractor,
    JavaTypeExtractor,
    JavaPersistenceExtractor,
    JavaEventExtractor,
    JavaTestExtractor,
    JavaConfigurationExtractor,
)


class JavaLanguageAdapter(BaseLanguageAdapter):
    """
    Language adapter for Java repositories.

    Uses focused extractors for all semantic categories, then compiles
    the extracted data into a RepositoryModel via the shared ModelCompiler.

    Note: This is a simplified implementation using regex-based parsing.
    A production version would use a proper Java parser like JavaParser.
    """

    def __init__(self):
        """Initialize the adapter with its extractors and compiler."""
        self._symbol_extractor = JavaSymbolExtractor()
        self._import_extractor = JavaImportExtractor()
        self._call_extractor = JavaCallExtractor()
        self._entrypoint_extractor = JavaEntrypointExtractor()
        self._type_extractor = JavaTypeExtractor()
        self._persistence_extractor = JavaPersistenceExtractor()
        self._event_extractor = JavaEventExtractor()
        self._test_extractor = JavaTestExtractor()
        self._configuration_extractor = JavaConfigurationExtractor()
        self._compiler = ModelCompiler()

    def get_language(self) -> str:
        """Get the language name this adapter handles."""
        return "java"

    def get_compiler_passes(self) -> list[str]:
        """Get the names of compiler passes this adapter uses."""
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
        semantic_graph = self._build_semantic_graph(files)
        return self._compiler.compile(semantic_graph, self.get_language())

    def _build_semantic_graph(self, files: dict[str, str]) -> dict[str, dict[str, Any]]:
        """
        Build a semantic graph from Java source files using extractors.

        Args:
            files: Dictionary mapping file paths to file contents

        Returns:
            Semantic graph dictionary
        """
        semantic_graph: dict[str, dict[str, Any]] = {}

        for file_path, content in files.items():
            if not file_path.endswith('.java'):
                continue

            try:
                lines = content.split('\n')
            except Exception:
                continue

            file_data = self._extract_file_data(lines, file_path)
            if file_data:
                semantic_graph[file_path] = file_data

        return semantic_graph

    def _extract_file_data(self, lines: list[str], file_path: str) -> dict[str, Any] | None:
        """
        Extract all semantic data from a Java source file using extractors.

        Args:
            lines: List of lines from the source file
            file_path: Path to the source file

        Returns:
            Dictionary with extracted semantic data
        """
        symbols = self._symbol_extractor.extract(lines, file_path)
        imports = self._import_extractor.extract(lines, file_path)
        calls = self._call_extractor.extract(lines, file_path)
        endpoints = self._entrypoint_extractor.extract(lines, file_path)
        type_relationships = self._type_extractor.extract(lines, file_path)
        persistence_models = self._persistence_extractor.extract(lines, file_path)
        event_constructs = self._event_extractor.extract(lines, file_path)
        test_definitions = self._test_extractor.extract(lines, file_path)
        configuration_references = self._configuration_extractor.extract(lines, file_path)

        # Separate symbols into functions and classes
        functions = [s for s in symbols if s['type'] == 'function']
        classes = [s for s in symbols if s['type'] == 'class']

        return {
            'language': 'java',
            'functions': functions,
            'classes': classes,
            'imports': imports,
            'function_calls': calls,
            'rest_endpoints': endpoints,
            'type_relationships': type_relationships,
            'persistence_models': persistence_models,
            'event_constructs': event_constructs,
            'test_definitions': test_definitions,
            'configuration_references': configuration_references,
        }
