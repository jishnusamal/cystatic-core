"""Python configuration index pass - detects configuration references from Python AST.

Emits only raw configuration facts. No resolution, no inference.
"""

import ast
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from engine.repository.model.repository_index import ConfigEntry


class PythonConfigurationIndexPass(BaseIndexPass):
    """Index pass that extracts configuration reference facts from Python AST.

    Detects environment variable access patterns (os.environ.get, os.getenv).
    No semantic inference — just structural configuration discovery.

    Supports both the visitor pattern (visit_Call) and the traditional
    process() method for backward compatibility.
    """

    CONFIG_PATTERNS = {
        "os.environ.get": "environment_variable",
        "os.getenv": "environment_variable",
        "os.environ.__getitem__": "environment_variable",
        "config.get": "config_file",
        "config.getint": "config_file",
        "settings.get": "settings",
    }

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract configuration references from a Python file context (legacy mode)."""
        tree = context.ast
        file_path = context.path

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                config = self._extract_config(node, file_path)
                if config:
                    builder["configurations"].append(config)

    def visit_Call(self, node: ast.Call, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle function call node from visitor."""
        config = self._extract_config(node, context.path)
        if config:
            builder["configurations"].append(config)

    def _extract_config(self, node: ast.Call, file_path: str) -> ConfigEntry | None:
        """Extract a configuration reference from a function call."""
        func_str = self._call_to_string(node.func)
        if func_str not in self.CONFIG_PATTERNS:
            return None

        kind = self.CONFIG_PATTERNS[func_str]
        symbol_name = self._get_enclosing_function_name(node) or ""

        config_key = ""
        if node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                config_key = first_arg.value

        default_value = ""
        if len(node.args) > 1:
            second_arg = node.args[1]
            if isinstance(second_arg, ast.Constant):
                default_value = str(second_arg.value)
        elif node.keywords:
            for kw in node.keywords:
                if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                    default_value = str(kw.value.value)
                    break

        if not config_key:
            return None

        return ConfigEntry(
            symbol_name=symbol_name,
            config_key=config_key,
            kind=kind,
            file=file_path,
            line=node.lineno,
            default_value=default_value,
        )

    def _call_to_string(self, node: ast.AST) -> str:
        """Convert a call node to a string representation for pattern matching."""
        if isinstance(node, ast.Attribute):
            parts = []
            current: ast.AST = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        elif isinstance(node, ast.Name):
            return node.id
        return ""

    def _get_enclosing_function_name(self, call_node: ast.Call) -> str | None:
        """Get the name of the function containing this call."""
        for parent in ast.walk(call_node):
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return parent.name
        return None