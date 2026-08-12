"""Python composite visitor - walks Python AST once and dispatches to all indexing passes.

This replaces multiple independent AST walks with a single traversal.
Each indexing pass registers as a collector and receives node events.
"""

import ast
import time
from typing import Any

from engine.language.base.visitors import BaseVisitor
from engine.language.base.file_context import FileContext
from engine.language.base.instrumentation import get_instrumentation


class PythonVisitor(BaseVisitor[ast.AST]):
    """Composite visitor for Python AST.

    Walks the AST exactly once per file and dispatches node events
    to all registered indexing passes. Each pass receives the same
    node events but maintains its own independent state in the builder.

    This ensures:
    - Single AST traversal per file
    - No duplicate parsing
    - Cache-friendly sequential access
    """

    def visit(self, context: FileContext[ast.AST], builder: dict[str, Any]) -> None:
        """Walk the AST once and dispatch to all registered collectors.

        Args:
            context: FileContext with parsed Python AST
            builder: Mutable builder dict for collected facts
        """
        inst = get_instrumentation()
        tree = context.ast
        file_path = context.path

        # Count AST nodes
        ast_nodes = 0
        for _ in ast.walk(tree):
            ast_nodes += 1
        inst.increment_counter("Visitor", "ast_nodes_visited", ast_nodes)

        # Walk top-level nodes
        for node in ast.iter_child_nodes(tree):
            self._dispatch(node, context, builder)

    def _dispatch(self, node: ast.AST, context: FileContext[ast.AST], builder: dict[str, Any]) -> None:
        """Dispatch a node to all registered collectors.

        Args:
            node: AST node to dispatch
            context: FileContext with parsed AST
            builder: Mutable builder dict for collected facts
        """
        inst = get_instrumentation()
        
        # Dispatch based on node type
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inst.increment_counter("Visitor", "functions_visited")
            self._visit_FunctionDef(node, context, builder)
        elif isinstance(node, ast.ClassDef):
            inst.increment_counter("Visitor", "classes_visited")
            self._visit_ClassDef(node, context, builder)
            # Don't recurse into ClassDef - the ClassDef handler extracts methods
            return
        elif isinstance(node, ast.Import):
            inst.increment_counter("Visitor", "imports_visited")
            self._visit_Import(node, context, builder)
        elif isinstance(node, ast.ImportFrom):
            inst.increment_counter("Visitor", "imports_visited")
            self._visit_ImportFrom(node, context, builder)
        elif isinstance(node, ast.Call):
            inst.increment_counter("Visitor", "calls_visited")
            self._visit_Call(node, context, builder)

        # Recursively walk child nodes for nested structures
        # (but not into ClassDef - handled above)
        for child in ast.iter_child_nodes(node):
            self._dispatch(child, context, builder)

    def _visit_FunctionDef(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, context: FileContext[ast.AST], builder: dict[str, Any]
    ) -> None:
        """Dispatch function definition to all collectors."""
        inst = get_instrumentation()
        
        for collector in self._collectors:
            if hasattr(collector, 'visit_FunctionDef'):
                pass_name = type(collector).__name__
                
                start = time.perf_counter()
                try:
                    collector.visit_FunctionDef(node, context, builder)
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_FunctionDef", elapsed)

    def _visit_ClassDef(self, node: ast.ClassDef, context: FileContext[ast.AST], builder: dict[str, Any]) -> None:
        """Dispatch class definition to all collectors."""
        inst = get_instrumentation()
        
        for collector in self._collectors:
            if hasattr(collector, 'visit_ClassDef'):
                pass_name = type(collector).__name__
                
                start = time.perf_counter()
                try:
                    collector.visit_ClassDef(node, context, builder)
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_ClassDef", elapsed)

    def _visit_Import(self, node: ast.Import, context: FileContext[ast.AST], builder: dict[str, Any]) -> None:
        """Dispatch import statement to all collectors."""
        inst = get_instrumentation()
        
        for collector in self._collectors:
            if hasattr(collector, 'visit_Import'):
                pass_name = type(collector).__name__
                
                start = time.perf_counter()
                try:
                    collector.visit_Import(node, context, builder)
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_Import", elapsed)

    def _visit_ImportFrom(self, node: ast.ImportFrom, context: FileContext[ast.AST], builder: dict[str, Any]) -> None:
        """Dispatch from-import statement to all collectors."""
        inst = get_instrumentation()
        
        for collector in self._collectors:
            if hasattr(collector, 'visit_ImportFrom'):
                pass_name = type(collector).__name__
                
                start = time.perf_counter()
                try:
                    collector.visit_ImportFrom(node, context, builder)
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_ImportFrom", elapsed)

    def _visit_Call(self, node: ast.Call, context: FileContext[ast.AST], builder: dict[str, Any]) -> None:
        """Dispatch function call to all collectors."""
        inst = get_instrumentation()
        
        for collector in self._collectors:
            if hasattr(collector, 'visit_Call'):
                pass_name = type(collector).__name__
                
                start = time.perf_counter()
                try:
                    collector.visit_Call(node, context, builder)
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_Call", elapsed)


__all__ = ["PythonVisitor"]