"""Test parser — detects test cases and their targets.

Detects:
    pytest, fixtures, parametrize, database marker, integration marker,
    mock, patch, target function, assertions
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    TestNode,
    FunctionNode,
    TestsEdge,
    UsesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class TestParser(GraphBuilder):
    """Extracts test cases and their relationships to tested functions."""

    _TEST_PREFIXES: Set[str] = {"test_", "test"}

    _FIXTURE_DECORATORS: Set[str] = {"fixture", "pytest.fixture"}

    _MARKERS: Dict[str, str] = {
        "django_db": "db",
        "pytest.mark.django_db": "db",
        "integration": "integration",
        "pytest.mark.integration": "integration",
        "e2e": "e2e",
        "pytest.mark.e2e": "e2e",
        "slow": "slow",
        "pytest.mark.slow": "slow",
    }

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        # Only process test files
        if "/test_" not in file_path and not file_path.startswith("test_"):
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_test(node, graph, file_path)

        return graph

    def _extract_test(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        name = func_node.name

        # Check if this is a test function
        is_test = any(name.startswith(prefix) for prefix in self._TEST_PREFIXES)
        if not is_test:
            return

        # Determine test type from markers
        test_type = "unit"
        uses_database = False
        uses_mock = False
        fixtures: List[str] = []
        is_parametrized = False
        target_functions: List[str] = []

        for dec in func_node.decorator_list:
            dec_str = ast.unparse(dec)

            # Markers
            for marker, marker_type in self._MARKERS.items():
                if marker in dec_str:
                    if marker_type == "db":
                        uses_database = True
                        test_type = "integration"
                    elif marker_type == "integration":
                        test_type = "integration"
                    elif marker_type == "e2e":
                        test_type = "e2e"

            # Fixtures
            if "fixture" in dec_str or "pytest.fixture" in dec_str:
                fixtures.append(dec_str)

            # Parametrize
            if "parametrize" in dec_str or "pytest.mark.parametrize" in dec_str:
                is_parametrized = True

        # Check function body for mock usage and target functions
        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute):
                    # mock.patch()
                    if func.attr == "patch" or func.attr == "patch.object":
                        uses_mock = True
                        # Extract target from first argument
                        if child.args:
                            arg = child.args[0]
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                target_functions.append(arg.value)

                    # Mock usage
                    if func.attr in {"assert_called", "assert_called_once",
                                     "assert_called_with", "assert_called_once_with"}:
                        uses_mock = True

        # Create test node
        test = TestNode(
            name=name,
            file_path=file_path,
            test_type=test_type,
            framework="pytest",
            target_functions=target_functions,
            uses_database=uses_database,
            uses_mock=uses_mock,
            uses_fixtures=fixtures,
            is_parametrized=is_parametrized,
        )
        graph.add_node(test)

        # Add TESTS edges to target functions
        for target in target_functions:
            target_node = G.ensure_function(graph, target, file_path)
            graph.add_edge(TestsEdge(source=test, target=target_node))