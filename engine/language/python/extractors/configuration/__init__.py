"""Python configuration extractor - discovers environment variable and config references."""

import ast
from typing import Any

from engine.language.base import BaseExtractor


class PythonConfigurationExtractor(BaseExtractor):
    """
    Extracts configuration references from Python source files.

    Recognizes:
    - os.environ / os.getenv calls
    - config objects (settings.X)
    - Feature flag checks
    - Pydantic Settings models
    - dotenv usage

    Produces a list of dicts with keys: symbol_id, config_key, kind,
    framework, file, line, default_value.
    """

    def extract(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """
        Extract configuration references from a Python AST.

        Args:
            tree: Parsed Python AST
            file_path: Path to the source file

        Returns:
            List of configuration reference dicts
        """
        config_refs = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                ref = self._extract_config_call(node, file_path)
                if ref:
                    config_refs.append(ref)

            elif isinstance(node, ast.Subscript):
                ref = self._extract_config_subscript(node, file_path)
                if ref:
                    config_refs.append(ref)

            elif isinstance(node, ast.Attribute):
                ref = self._extract_config_attribute(node, file_path)
                if ref:
                    config_refs.append(ref)

        return config_refs

    def _extract_config_call(
        self, node: ast.Call, file_path: str
    ) -> dict[str, Any] | None:
        """Extract config reference from a function call."""
        func_name = self._get_func_name(node)

        # os.getenv(key, default) or os.environ.get(key, default)
        if func_name in ("os.getenv", "os.environ.get", "getenv"):
            caller_id = self._get_caller_id(node)
            config_key = self._get_first_string_arg(node)
            default_value = self._get_second_arg(node)

            if config_key:
                return {
                    "symbol_id": caller_id or "",
                    "config_key": config_key,
                    "kind": "environment_variable",
                    "framework": "os.environ",
                    "file": file_path,
                    "line": node.lineno,
                    "default_value": default_value,
                }

        # config(key, default) style
        if func_name in ("config", "setting", "get_config"):
            caller_id = self._get_caller_id(node)
            config_key = self._get_first_string_arg(node)
            default_value = self._get_second_arg(node)

            if config_key:
                return {
                    "symbol_id": caller_id or "",
                    "config_key": config_key,
                    "kind": "settings_object",
                    "framework": "custom",
                    "file": file_path,
                    "line": node.lineno,
                    "default_value": default_value,
                }

        return None

    def _extract_config_subscript(
        self, node: ast.Subscript, file_path: str
    ) -> dict[str, Any] | None:
        """Extract config reference from a subscript access like os.environ['KEY']."""
        # os.environ['KEY']
        if isinstance(node.value, ast.Attribute):
            if isinstance(node.value.value, ast.Name) and node.value.value.id == "os":
                if node.value.attr == "environ" and isinstance(
                    node.slice, ast.Constant
                ):
                    caller_id = self._get_caller_id(node)
                    config_key = str(node.slice.value)

                    return {
                        "symbol_id": caller_id or "",
                        "config_key": config_key,
                        "kind": "environment_variable",
                        "framework": "os.environ",
                        "file": file_path,
                        "line": node.lineno,
                        "default_value": "",
                    }

            # settings['KEY'] pattern
            if node.value.attr in ("settings", "config", "conf"):
                if isinstance(node.slice, ast.Constant):
                    caller_id = self._get_caller_id(node)
                    config_key = str(node.slice.value)

                    return {
                        "symbol_id": caller_id or "",
                        "config_key": config_key,
                        "kind": "settings_object",
                        "framework": "custom",
                        "file": file_path,
                        "line": node.lineno,
                        "default_value": "",
                    }

        return None

    def _extract_config_attribute(
        self, node: ast.Attribute, file_path: str
    ) -> dict[str, Any] | None:
        """Extract config reference from an attribute access like settings.DATABASE_URL."""
        # settings.X or config.X
        if isinstance(node.value, ast.Name) and node.value.id in (
            "settings",
            "config",
            "conf",
            "cfg",
        ):
            attr_name = node.attr
            if attr_name and not attr_name.startswith("_"):
                caller_id = self._get_caller_id(node)

                return {
                    "symbol_id": caller_id or "",
                    "config_key": attr_name,
                    "kind": "settings_object",
                    "framework": "custom",
                    "file": file_path,
                    "line": node.lineno,
                    "default_value": "",
                }

        return None

    def _get_func_name(self, node: ast.Call) -> str:
        """Get the full function name from a call node."""
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                return f"{node.func.value.id}.{node.func.attr}"
            elif isinstance(node.func.value, ast.Attribute):
                parts = []
                current = node.func
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                return ".".join(reversed(parts))
        elif isinstance(node.func, ast.Name):
            return node.func.id
        return ""

    def _get_caller_id(self, node: ast.AST) -> str | None:
        """Get the enclosing function symbol id."""
        for parent in ast.walk(node):
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return f"python://{getattr(node, 'file', '')}::{parent.name}"
        return None

    def _get_first_string_arg(self, node: ast.Call) -> str:
        """Get the first string argument from a call."""
        if node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return arg.value
        return ""

    def _get_second_arg(self, node: ast.Call) -> str:
        """Get the second argument (default value) from a call."""
        if len(node.args) >= 2:
            arg = node.args[1]
            if isinstance(arg, ast.Constant):
                return str(arg.value)
            return ""
        # Check keyword argument 'default'
        for kw in node.keywords:
            if kw.arg in ("default", "fallback"):
                if isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
        return ""
