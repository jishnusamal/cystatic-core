"""Python test extractor - discovers test classes, methods, fixtures, and assertions."""

import ast
from typing import Any

from engine.language.base import BaseExtractor


class PythonTestExtractor(BaseExtractor):
    """
    Extracts test definitions from Python source files.

    Recognizes:
    - pytest test functions and classes
    - unittest TestCase subclasses
    - pytest fixtures
    - Doctests

    Produces a list of dicts with keys: symbol_id, name, kind, framework,
    file, line, fixtures, assertions.
    """

    PYTEST_PREFIX = "test_"
    UNITTEST_BASE = "TestCase"

    def extract(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """
        Extract test definitions from a Python AST.

        Args:
            tree: Parsed Python AST
            file_path: Path to the source file

        Returns:
            List of test definition dicts
        """
        tests = []
        fixtures = self._collect_fixtures(tree, file_path)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                test = self._extract_test_function(node, file_path, fixtures)
                if test:
                    tests.append(test)

            elif isinstance(node, ast.ClassDef):
                test_class = self._extract_test_class(node, file_path, fixtures)
                if test_class:
                    tests.append(test_class)

        return tests

    def _collect_fixtures(
        self, tree: ast.AST, file_path: str
    ) -> dict[str, dict[str, Any]]:
        """Collect all pytest fixture definitions."""
        fixtures = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                decorators = self._get_decorator_names(node)
                if "fixture" in decorators:
                    scope = "function"
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Call) and dec.args:
                            for kw in dec.keywords:
                                if kw.arg == "scope" and isinstance(
                                    kw.value, ast.Constant
                                ):
                                    scope = str(kw.value.value)

                    fixtures[node.name] = {
                        "name": node.name,
                        "scope": scope,
                        "symbol_id": f"python://{file_path}::{node.name}",
                        "file": file_path,
                        "line": node.lineno,
                    }
        return fixtures

    def _extract_test_function(
        self, node: ast.FunctionDef, file_path: str, fixtures: dict
    ) -> dict[str, Any] | None:
        """Extract a test function definition."""
        framework = self._detect_framework(node)

        # Not a test function
        if framework == "unknown":
            return None

        symbol_id = f"python://{file_path}::{node.name}"
        used_fixtures = self._find_used_fixtures(node, fixtures)
        assertions = self._find_assertions(node)

        return {
            "symbol_id": symbol_id,
            "name": node.name,
            "kind": "function",
            "framework": framework,
            "file": file_path,
            "line": node.lineno,
            "fixtures": used_fixtures,
            "assertions": assertions,
        }

    def _extract_test_class(
        self, node: ast.ClassDef, file_path: str, fixtures: dict
    ) -> dict[str, Any] | None:
        """Extract a test class definition with its test methods."""
        framework = self._detect_class_framework(node)
        if framework == "unknown":
            return None

        class_symbol_id = f"python://{file_path}#{node.name}"
        test_methods = []

        for child in node.body:
            if isinstance(child, ast.FunctionDef) and (
                child.name.startswith("test_") or child.name.startswith("test")
            ):
                method_sym = f"python://{file_path}#{node.name}.{child.name}"
                used_fixtures = self._find_used_fixtures(child, fixtures)
                assertions = self._find_assertions(child)

                test_methods.append(
                    {
                        "symbol_id": method_sym,
                        "name": child.name,
                        "kind": "method",
                        "framework": framework,
                        "file": file_path,
                        "line": child.lineno,
                        "fixtures": used_fixtures,
                        "assertions": assertions,
                    }
                )

        return {
            "symbol_id": class_symbol_id,
            "name": node.name,
            "kind": "class",
            "framework": framework,
            "file": file_path,
            "line": node.lineno,
            "fixtures": [],
            "assertions": [],
            "test_methods": test_methods,
        }

    def _detect_framework(self, node: ast.FunctionDef) -> str:
        """Detect the test framework for a function."""
        if node.name.startswith(self.PYTEST_PREFIX):
            return "pytest"
        return "unknown"

    def _detect_class_framework(self, node: ast.ClassDef) -> str:
        """Detect the test framework for a class."""
        # Check for unittest TestCase inheritance
        for base in node.bases:
            base_str = self._base_to_string(base)
            if "TestCase" in base_str:
                return "unittest"

        # Check for pytest naming convention
        if node.name.startswith("Test"):
            return "pytest"

        return "unknown"

    def _base_to_string(self, node: ast.AST) -> str:
        """Convert a base class node to a string representation."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""

    def _get_decorator_names(self, node: ast.FunctionDef) -> list[str]:
        """Get decorator names from a function."""
        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Attribute) and isinstance(dec.value, ast.Name):
                decorators.append(f"{dec.value.id}.{dec.attr}")
            elif isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
        return decorators

    def _find_used_fixtures(
        self, node: ast.FunctionDef, fixtures: dict
    ) -> list[dict[str, Any]]:
        """Find which fixtures are used by a test function."""
        used = []
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in fixtures:
                used.append(fixtures[child.id])
        return used

    def _find_assertions(self, node: ast.FunctionDef) -> list[str]:
        """Find assertion types used in a test function."""
        assertions = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                name = child.func.attr
                if name.startswith("assert") or name in (
                    "assertEqual",
                    "assertTrue",
                    "assertFalse",
                    "assertIs",
                    "assertIsNot",
                    "assertIsNone",
                    "assertIsNotNone",
                    "assertIn",
                    "assertNotIn",
                    "assertRaises",
                    "assertGreater",
                    "assertLess",
                    "fail",
                ):
                    assertions.add(name)
        return list(assertions)
