"""Python call index pass - extracts function calls from Python AST.

Emits only raw call facts. No resolution, no symbol matching.
Callee names are stored as raw text — no attempt to resolve references.
"""

import ast
import time
from typing import Any

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.language.base.instrumentation import get_instrumentation
from engine.repository.model.repository_index import CallEntry


class PythonCallIndexPass(BaseIndexPass):
    """Index pass that extracts call facts from Python AST.

    Extracts: caller function name, callee name, call type, line.
    No resolution of what the callee refers to — that's semantic compilation.

    Supports both the visitor pattern (visit_Call) and the traditional
    process() method for backward compatibility.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract calls from a Python file context (legacy mode)."""
        inst = get_instrumentation()
        tree = context.ast
        file_path = context.path

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                caller_name, caller_parent = self._get_caller_info_optimized(node, tree)
                callee_name, receiver = self._get_callee_info(node)

                if caller_name and callee_name:
                    builder["calls"].append(
                        CallEntry(
                            caller=caller_name,
                            callee=callee_name,
                            call_type="direct",
                            file=file_path,
                            line=node.lineno,
                            receiver=receiver,
                            caller_parent=caller_parent,
                        )
                    )

    def visit_Call(self, node: ast.Call, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle function call node from visitor."""
        inst = get_instrumentation()
        tree = context.ast
        file_path = context.path
        
        # Time the entire visit_Call
        start = time.perf_counter()
        try:
            # Use parent map for O(1) caller lookup instead of O(n*m) AST walk
            caller_name, caller_parent = self._get_caller_info_optimized(node, tree)
            callee_name, receiver = self._get_callee_info(node)

            if caller_name and callee_name:
                builder["calls"].append(
                    CallEntry(
                        caller=caller_name,
                        callee=callee_name,
                        call_type="direct",
                        file=file_path,
                        line=node.lineno,
                        receiver=receiver,
                        caller_parent=caller_parent,
                    )
                )
        finally:
            elapsed = time.perf_counter() - start
            inst.record_method_time("PythonCallIndexPass", "visit_Call", elapsed)

    def visit_ClassDef(self, node: ast.ClassDef, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle calls inside class methods by walking the class body."""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                self.visit_Call(child, context, builder)

    def _get_caller_name(self, call_node: ast.Call, tree: ast.AST) -> str | None:
        """Get the name of the function containing this call (legacy O(n*m) implementation)."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self._node_contains(call_node, node):
                    return node.name
        return None

    def _get_caller_name_optimized(self, call_node: ast.Call, tree: ast.AST) -> str | None:
        """Get the name of the function containing this call."""
        caller_name, _ = self._get_caller_info_optimized(call_node, tree)
        return caller_name

    def _get_caller_info_optimized(self, call_node: ast.Call, tree: ast.AST) -> tuple[str | None, str]:
        """Get caller function name and optional enclosing class name."""
        inst = get_instrumentation()
        
        start = time.perf_counter()
        try:
            parent_map = self._get_parent_map(tree)
            current: ast.AST | None = call_node
            caller_name: str | None = None
            caller_parent = ""

            while current:
                parent = parent_map.get(id(current))
                if parent is None:
                    break
                if caller_name is None and isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    caller_name = parent.name
                elif caller_name is not None and isinstance(parent, ast.ClassDef):
                    caller_parent = parent.name
                    break
                elif caller_name is not None and isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    break
                current = parent

            return caller_name, caller_parent
        finally:
            elapsed = time.perf_counter() - start
            inst.record_method_time("PythonCallIndexPass", "_get_caller_name_optimized", elapsed)

    def _get_callee_name(self, call_node: ast.Call) -> str | None:
        """Get the raw name of the called function."""
        callee_name, _ = self._get_callee_info(call_node)
        return callee_name

    def _get_callee_info(self, call_node: ast.Call) -> tuple[str | None, str]:
        """Get callee name and receiver expression string."""
        inst = get_instrumentation()
        
        start = time.perf_counter()
        try:
            if isinstance(call_node.func, ast.Name):
                return call_node.func.id, ""
            elif isinstance(call_node.func, ast.Attribute):
                receiver = self._get_receiver_string(call_node.func.value)
                return call_node.func.attr, receiver
            return None, ""
        finally:
            elapsed = time.perf_counter() - start
            inst.record_internal_op("PythonCallIndexPass", "visit_Call", 
                                  "_get_callee_name", elapsed)

    def _get_receiver_string(self, node: ast.AST) -> str:
        """Convert a receiver AST node to a dot-separated string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._get_receiver_string(node.value)
            return f"{val}.{node.attr}" if val else node.attr
        return ""

    def _get_parent_map(self, tree: ast.AST) -> dict[int, ast.AST]:
        """Build a parent map for the AST.
        
        Maps each node's id() to its parent node.
        This is cached on the tree object to avoid rebuilding.
        
        Returns:
            Dictionary mapping node id to parent node
        """
        # Cache parent map on tree object to avoid rebuilding
        pm: dict[int, ast.AST] | None = getattr(tree, '_parent_map', None)
        if pm is None:
            pm = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    pm[id(child)] = node
            setattr(tree, '_parent_map', pm)
        
        return pm

    def _node_contains(self, inner: ast.AST, outer: ast.AST) -> bool:
        """Check if inner node is contained within outer node (legacy implementation)."""
        # This is kept for backward compatibility but no longer used
        for child in ast.walk(outer):
            if child is inner:
                return True
        return False
