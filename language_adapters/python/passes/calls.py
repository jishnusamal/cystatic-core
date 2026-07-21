"""Python call index pass - extracts function calls from Python AST.

Emits only raw call facts. No resolution, no symbol matching.
Callee names are stored as raw text — no attempt to resolve references.
"""

import ast
import time
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from language_adapters.base.instrumentation import get_instrumentation
from language_adapters.model.repository_index import CallEntry


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
                caller_name = self._get_caller_name(node, tree)
                callee_name = self._get_callee_name(node)

                if caller_name and callee_name:
                    builder["calls"].append(
                        CallEntry(
                            caller=caller_name,
                            callee=callee_name,
                            call_type="direct",
                            file=file_path,
                            line=node.lineno,
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
            caller_name = self._get_caller_name_optimized(node, tree)
            callee_name = self._get_callee_name(node)

            if caller_name and callee_name:
                builder["calls"].append(
                    CallEntry(
                        caller=caller_name,
                        callee=callee_name,
                        call_type="direct",
                        file=file_path,
                        line=node.lineno,
                    )
                )
        finally:
            elapsed = time.perf_counter() - start
            inst.record_method_time("PythonCallIndexPass", "visit_Call", elapsed)

    def _get_caller_name(self, call_node: ast.Call, tree: ast.AST) -> str | None:
        """Get the name of the function containing this call (legacy O(n*m) implementation)."""
        # This is the old implementation kept for reference but not used
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self._node_contains(call_node, node):
                    return node.name
        return None

    def _get_caller_name_optimized(self, call_node: ast.Call, tree: ast.AST) -> str | None:
        """Get the name of the function containing this call (optimized O(depth) implementation).
        
        Builds a parent map once, then walks up from call_node to find enclosing function.
        This is O(n) to build + O(depth) per call, instead of O(n*m) for m calls.
        """
        inst = get_instrumentation()
        
        start = time.perf_counter()
        try:
            # Build parent map once per file (cached on tree)
            parent_map = self._get_parent_map(tree)
            
            # Walk up from call_node to find enclosing function
            current = call_node
            while current:
                parent = parent_map.get(id(current))
                if parent is None:
                    # Reached root
                    break
                
                # Check if parent is a function
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return parent.name
                
                current = parent
            
            return None
        finally:
            elapsed = time.perf_counter() - start
            inst.record_method_time("PythonCallIndexPass", "_get_caller_name_optimized", elapsed)

    def _get_callee_name(self, call_node: ast.Call) -> str | None:
        """Get the raw name of the called function."""
        inst = get_instrumentation()
        
        start = time.perf_counter()
        try:
            if isinstance(call_node.func, ast.Name):
                return call_node.func.id
            elif isinstance(call_node.func, ast.Attribute):
                return call_node.func.attr
            return None
        finally:
            elapsed = time.perf_counter() - start
            inst.record_internal_op("PythonCallIndexPass", "visit_Call", 
                                  "_get_callee_name", elapsed)

    def _get_parent_map(self, tree: ast.AST) -> dict[int, ast.AST]:
        """Build a parent map for the AST.
        
        Maps each node's id() to its parent node.
        This is cached on the tree object to avoid rebuilding.
        
        Returns:
            Dictionary mapping node id to parent node
        """
        # Cache parent map on tree object to avoid rebuilding
        if not hasattr(tree, '_parent_map'):
            parent_map: dict[int, ast.AST] = {}
            
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parent_map[id(child)] = node
            
            tree._parent_map = parent_map
        
        return tree._parent_map

    def _node_contains(self, inner: ast.AST, outer: ast.AST) -> bool:
        """Check if inner node is contained within outer node (legacy implementation)."""
        # This is kept for backward compatibility but no longer used
        for child in ast.walk(outer):
            if child is inner:
                return True
        return False
