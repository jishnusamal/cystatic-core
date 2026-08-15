"""Python entrypoint extractor - detects REST API endpoints from Python AST."""

import ast
from typing import Any

from engine.language.base import BaseExtractor


# HTTP methods that indicate a REST endpoint decorator
HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch"})


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
                for dec in node.decorator_list:
                    # Check if this is a decorator call like @router.post("/route")
                    if isinstance(dec, ast.Call) and isinstance(
                        dec.func, ast.Attribute
                    ):
                        if isinstance(dec.func.value, ast.Name):
                            method = dec.func.attr.lower()
                            if method in HTTP_METHODS and dec.args:
                                route = self._get_arg_value(dec.args[0])
                                if route:
                                    endpoints.append(
                                        {
                                            "method": method.upper(),
                                            "route": route,
                                            "handler": node.name,
                                        }
                                    )

        return endpoints

    def _get_arg_value(self, node: ast.AST) -> str | None:
        """Get string value from an AST node."""
        if isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Str):  # Python 3.7 compatibility
            return node.s
        return None
