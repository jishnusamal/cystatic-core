"""Python symbol extractor - extracts functions, classes, and methods from Python AST."""

import ast
from typing import Any

from language_adapters.base import BaseExtractor


class PythonSymbolExtractor(BaseExtractor):
    """
    Extracts function, class, and method definitions from Python source files.
    
    Produces a list of dicts with keys: name, start_line, end_line, visibility, properties.
    """
    
    def extract(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """
        Extract all symbols from a Python AST.
        
        Args:
            tree: Parsed Python AST
            file_path: Path to the source file
            
        Returns:
            List of symbol dicts with type, name, start_line, end_line, visibility, properties
        """
        symbols = []
        
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                symbols.append(self._extract_function(node))
            elif isinstance(node, ast.ClassDef):
                symbols.append(self._extract_class(node))
        
        return symbols
    
    def _extract_function(self, node: ast.FunctionDef) -> dict[str, Any]:
        """Extract a function definition."""
        return {
            'type': 'function',
            'name': node.name,
            'start_line': node.lineno,
            'end_line': node.end_lineno or node.lineno,
            'visibility': self._determine_visibility(node),
            'properties': self._extract_function_properties(node),
        }
    
    def _extract_class(self, node: ast.ClassDef) -> dict[str, Any]:
        """Extract a class definition with its methods."""
        methods = []
        for child in node.body:
            if isinstance(child, ast.FunctionDef):
                methods.append({
                    'name': child.name,
                    'start_line': child.lineno,
                    'end_line': child.end_lineno or child.lineno,
                    'class_name': node.name,
                    'visibility': self._determine_visibility(child),
                })
        
        return {
            'type': 'class',
            'name': node.name,
            'start_line': node.lineno,
            'end_line': node.end_lineno or node.lineno,
            'visibility': self._determine_visibility(node),
            'methods': methods,
            'properties': self._extract_class_properties(node),
        }
    
    def _determine_visibility(self, node: ast.AST) -> str:
        """Determine symbol visibility from naming convention."""
        name = node.name if hasattr(node, 'name') else ''
        if name.startswith('_') and not name.startswith('__'):
            return 'private'
        elif name.startswith('__') and name.endswith('__'):
            return 'public'
        return 'public'
    
    def _extract_function_properties(self, node: ast.FunctionDef) -> dict[str, Any]:
        """Extract additional properties from a function."""
        properties = {}
        
        docstring = ast.get_docstring(node)
        if docstring:
            properties['docstring'] = docstring
        
        decorators = self._get_decorator_names(node)
        if decorators:
            properties['decorators'] = decorators
        
        return properties
    
    def _extract_class_properties(self, node: ast.ClassDef) -> dict[str, Any]:
        """Extract additional properties from a class."""
        properties = {}
        
        docstring = ast.get_docstring(node)
        if docstring:
            properties['docstring'] = docstring
        
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
        if bases:
            properties['bases'] = bases
        
        return properties
    
    def _get_decorator_names(self, node: ast.FunctionDef) -> list[str]:
        """Get decorator names from a function."""
        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Attribute):
                if isinstance(dec.value, ast.Name):
                    decorators.append(f"{dec.value.id}.{dec.attr}")
            elif isinstance(dec, ast.Name):
                decorators.append(dec.id)
        return decorators