"""Python entrypoint extractor - detects REST API endpoints from Python AST."""

import ast
from typing import Any

from language_adapters.base import BaseExtractor


class PythonEntrypointExtractor(BaseExtractor):
    """
    Detects REST API endpoints from decorators (FastAPI/Flask style).
    
    Produces a list of dicts with keys: method, route, handler.
    """
    
    def extract(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """
        Extract REST API endpoints from a Python AST.
        
        Args:
            tree: Parsed Python AST
            file_path: Path to the source file
            
        Returns:
            List of endpoint dicts with method, route, handler
        """
        endpoints = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = self._get_decorator_names(node)
                
                for dec in decorators:
                    if dec in (
                        'app.post', 'app.get', 'app.put', 'app.delete',
                        'app.patch', 'router.post', 'router.get',
                    ):
                        parts = dec.split('.')
                        if len(parts) >= 2:
                            method = parts[-1].upper()
                            route = self._get_decorator_arg(node, dec)
                            if route:
                                endpoints.append({
                                    'method': method,
                                    'route': route,
                                    'handler': node.name,
                                })
        
        return endpoints
    
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
    
    def _get_decorator_arg(self, node: ast.FunctionDef, decorator_name: str) -> str | None:
        """Get the argument of a decorator."""
        for dec in node.decorator_list:
            if isinstance(dec, ast.Attribute):
                if isinstance(dec.value, ast.Name):
                    full_name = f"{dec.value.id}.{dec.attr}"
                    if full_name == decorator_name and dec.args:
                        return self._get_arg_value(dec.args[0])
        return None
    
    def _get_arg_value(self, node: ast.AST) -> str | None:
        """Get string value from an AST node."""
        if isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Str):  # Python 3.7 compatibility
            return node.s
        return None