"""Python test index pass - discovers test definitions from Python AST.

Emits only raw test facts. No inference about test execution or coverage.
"""

import ast
from typing import Any

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import TestEntry


class PythonTestIndexPass(BaseIndexPass):
    """Index pass that extracts test facts from Python AST.

    Discovers test functions, test classes, and test methods.
    No execution analysis - just structural test discovery.

    Supports both the visitor pattern (visit_FunctionDef, visit_ClassDef)
    and the traditional process() method for backward compatibility.
    """

    PYTEST_PREFIX = "test_"

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract test definitions from a Python file context (legacy mode)."""
        tree = context.ast
        file_path = context.path

        # Collect fixtures first so test functions can reference them
        fixtures = self._collect_fixtures(tree, file_path)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                test = self._extract_test_function(node, file_path, fixtures)
                if test:
                    builder["tests"].append(test)

            elif isinstance(node, ast.ClassDef):
                test_class = self._extract_test_class(node, file_path, fixtures)
                if test_class:
                    builder["tests"].append(test_class)

    def visit_FunctionDef(self, node: ast.FunctionDef, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle function definition node from visitor."""
        # Note: In visitor mode, we can't pre-collect fixtures across the whole tree
        # so we skip fixture-aware test extraction and just check for test_ prefix
        if node.name.startswith(self.PYTEST_PREFIX):
            test = TestEntry(
                name=node.name,
                kind="function",
                framework="pytest",
                file=context.path,
                line=node.lineno,
                fixtures=tuple(),
                assertions=tuple(),
            )
            builder["tests"].append(test)

    def visit_ClassDef(self, node: ast.ClassDef, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle class definition node from visitor."""
        framework = self._detect_class_framework(node)
        if framework == "unknown":
            return

        test_methods = []
        for child in node.body:
            if isinstance(child, ast.FunctionDef):
                if child.name.startswith("test_") or child.name.startswith("test"):
                    test_methods.append(
                        TestEntry(
                            name=child.name,
                            kind="method",
                            framework=framework,
                            file=context.path,
                            line=child.lineno,
                            fixtures=tuple(),
                            assertions=tuple(),
                        )
                    )

        builder["tests"].append(
            TestEntry(
                name=node.name,
                kind="class",
                framework=framework,
                file=context.path,
                line=node.lineno,
                test_methods=tuple(test_methods),
            )
        )

    def _collect_fixtures(self, tree: ast.AST, file_path: str) -> dict[str, dict[str, Any]]:
        """Collect all pytest fixture definitions."""
        fixtures = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                decorators = self._get_decorator_names(node)
                if "fixture" in decorators:
                    scope = "function"
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Call):
                            for kw in dec.keywords or []:
                                if kw.arg == "scope" and isinstance(kw.value, ast.Constant):
                                    scope = str(kw.value.value)
                    fixtures[node.name] = {
                        "name": node.name,
                        "scope": scope,
                        "file": file_path,
                        "line": node.lineno,
                    }
        return fixtures

    def _extract_test_function(
        self,
        node: ast.FunctionDef,
        file_path: str,
        fixtures: dict,
    ) -> TestEntry | None:
        """Extract a test function definition."""
        if not node.name.startswith(self.PYTEST_PREFIX):
            return None

        used_fixtures = self._find_used_fixtures(node, fixtures)
        assertions = self._find_assertions(node)

        return TestEntry(
            name=node.name,
            kind="function",
            framework="pytest",
            file=file_path,
            line=node.lineno,
            fixtures=tuple(used_fixtures),
            assertions=tuple(assertions),
        )

    def _extract_test_class(
        self,
        node: ast.ClassDef,
        file_path: str,
        fixtures: dict,
    ) -> TestEntry | None:
        """Extract a test class definition with its test methods."""
        # Check for unittest TestCase inheritance
        framework = self._detect_class_framework(node)
        if framework == "unknown":
            return None

        test_methods = []
        for child in node.body:
            if isinstance(child, ast.FunctionDef):
                if child.name.startswith("test_") or child.name.startswith("test"):
                    used_fixtures = self._find_used_fixtures(child, fixtures)
                    assertions = self._find_assertions(child)
                    test_methods.append(
                        TestEntry(
                            name=child.name,
                            kind="method",
                            framework=framework,
                            file=file_path,
                            line=child.lineno,
                            fixtures=tuple(used_fixtures),
                            assertions=tuple(assertions),
                        )
                    )

        return TestEntry(
            name=node.name,
            kind="class",
            framework=framework,
            file=file_path,
            line=node.lineno,
            test_methods=tuple(test_methods),
        )

    def _detect_class_framework(self, node: ast.ClassDef) -> str:
        """Detect the test framework for a class."""
        for base in node.bases:
            base_str = self._base_to_string(base)
            if "TestCase" in base_str:
                return "unittest"
        if node.name.startswith("Test"):
            return "pytest"
        return "unknown"

    def _base_to_string(self, node: ast.AST) -> str:
        """Convert a base class node to a string representation."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            current: ast.AST = node
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
            if isinstance(dec, ast.Attribute):
                if isinstance(dec.value, ast.Name):
                    decorators.append(f"{dec.value.id}.{dec.attr}")
            elif isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    decorators.append(dec.func.id)
        return decorators

    def _find_used_fixtures(
        self,
        node: ast.FunctionDef,
        fixtures: dict,
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
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Attribute):
                    name = child.func.attr
                    if name.startswith("assert") or name in (
                        "assertEqual", "assertTrue", "assertFalse",
                        "assertIs", "assertIsNot", "assertIsNone",
                        "assertIsNotNone", "assertIn", "assertNotIn",
                        "assertRaises", "assertGreater", "assertLess", "fail",
                    ):
                        assertions.add(name)
        return list(assertions)