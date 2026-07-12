"""Python language adapter - compiles Python repositories to RepositoryModel."""

import ast
from typing import Any

from language_adapters.base import BaseLanguageAdapter, ModelCompiler
from language_adapters.model import RepositoryModel
from language_adapters.python.extractors import (
    PythonSymbolExtractor,
    PythonImportExtractor,
    PythonCallExtractor,
    PythonEntrypointExtractor,
)


class PythonLanguageAdapter(BaseLanguageAdapter):
    """
    Language adapter for Python repositories.
    
    Uses focused extractors for symbols, imports, calls, and entrypoints,
    then compiles the extracted data into a RepositoryModel via the shared ModelCompiler.
    """
    
    def __init__(self):
        """Initialize the adapter with its extractors and compiler."""
        self._symbol_extractor = PythonSymbolExtractor()
        self._import_extractor = PythonImportExtractor()
        self._call_extractor = PythonCallExtractor()
        self._entrypoint_extractor = PythonEntrypointExtractor()
        self._compiler = ModelCompiler()
    
    def get_language(self) -> str:
        """Get the language name this adapter handles."""
        return "python"
    
    def get_compiler_passes(self) -> list[str]:
        """Get the names of compiler passes this adapter uses."""
        return [
            "symbol_collection",
            "reference_resolution",
            "call_graph",
            "endpoint_discovery",
        ]
    
    def compile(self, repository_input: dict[str, Any]) -> RepositoryModel:
        """
        Compile a Python repository into a RepositoryModel.
        
        Args:
            repository_input: Repository snapshot containing:
                - files: dict[file_path, file_content] or pre-built semantic graph
                - language: str (should be "python")
        
        Returns:
            RepositoryModel: Language-independent repository representation
        """
        files = repository_input.get('files', {})
        
        # Check if files is already a semantic graph (for testing) or raw file contents
        if files and isinstance(next(iter(files.values())), dict):
            semantic_graph = files
        else:
            semantic_graph = self._build_semantic_graph(files)
        
        return self._compiler.compile(semantic_graph, self.get_language())
    
    def _build_semantic_graph(self, files: dict[str, str]) -> dict[str, dict[str, Any]]:
        """
        Build a semantic graph from Python source files using extractors.
        
        Args:
            files: Dictionary mapping file paths to file contents
        
        Returns:
            Semantic graph dictionary
        """
        semantic_graph: dict[str, dict[str, Any]] = {}
        
        for file_path, content in files.items():
            if not file_path.endswith('.py'):
                continue
            
            try:
                tree = ast.parse(content, filename=file_path)
            except SyntaxError:
                continue
            
            file_data = self._extract_file_data(tree, file_path)
            if file_data:
                semantic_graph[file_path] = file_data
        
        return semantic_graph
    
    def _extract_file_data(self, tree: ast.AST, file_path: str) -> dict[str, Any] | None:
        """
        Extract all semantic data from a parsed Python file using extractors.
        
        Args:
            tree: Parsed Python AST
            file_path: Path to the source file
        
        Returns:
            Dictionary with extracted semantic data
        """
        symbols = self._symbol_extractor.extract(tree, file_path)
        imports = self._import_extractor.extract(tree, file_path)
        calls = self._call_extractor.extract(tree, file_path)
        endpoints = self._entrypoint_extractor.extract(tree, file_path)
        
        # Separate symbols into functions and classes
        functions = [s for s in symbols if s['type'] == 'function']
        classes = [s for s in symbols if s['type'] == 'class']
        
        return {
            'language': 'python',
            'functions': functions,
            'classes': classes,
            'imports': imports,
            'function_calls': calls,
            'rest_endpoints': endpoints,
        }