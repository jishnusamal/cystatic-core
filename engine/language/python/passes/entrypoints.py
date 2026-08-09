"""Python entrypoint index pass - detects REST API endpoints from Python AST.

Emits only raw entrypoint facts. No handler resolution, no symbol matching.
"""

import ast
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from engine.repository.model.repository_index import EntrypointEntry

# HTTP methods that indicate a REST endpoint decorator
HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch"})


class PythonEntrypointIndexPass(BaseIndexPass):
    """Index pass that extracts entrypoint facts from Python AST.

    Detects REST API endpoints from decorators (FastAPI/Flask style).
    No handler resolution — just raw route, method, and handler name.

    Supports both the visitor pattern (visit_FunctionDef) and the traditional
    process() method for backward compatibility.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract entrypoints from a Python file context (legacy mode)."""
        tree = context.ast
        file_path = context.path

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_and_add_entrypoint(node, file_path, builder)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle function definition node from visitor."""
        self._check_and_add_entrypoint(node, context.path, builder)

    def _check_and_add_entrypoint(self, node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: str, builder: dict[str, Any]) -> None:
        """Check if a function has endpoint decorators and add entrypoint if found."""
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if isinstance(dec.func.value, ast.Name):
                    method = dec.func.attr.lower()
                    if method in HTTP_METHODS and dec.args:
                        route = self._get_arg_value(dec.args[0])
                        if route:
                            builder["entrypoints"].append(
                                EntrypointEntry(
                                    route=f"{method.upper()} {route}",
                                    handler=node.name,
                                    kind="rest_endpoint",
                                    file=file_path,
                                    line=node.lineno,
                                )
                            )

    def _get_arg_value(self, node: ast.AST) -> str | None:
        """Get string value from an AST node."""
        if isinstance(node, ast.Constant):
            return str(node.value) if node.value is not None else None
        elif isinstance(node, ast.Str):
            return str(node.s)
        return None