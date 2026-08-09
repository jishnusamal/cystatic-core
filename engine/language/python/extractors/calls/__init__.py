"""Python call extractor - extracts function calls from Python AST."""

import ast
from typing import Any

from engine.language.base import BaseExtractor


class PythonCallExtractor(BaseExtractor):
    """
    Extracts function call relationships from Python source files.
    
    Produces a list of dicts with keys: caller_id, callee_name, call_type.
    """
    
    def extract(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """
        Extract all function calls from a Python AST.
        
        Args:
            tree: Parsed Python AST
            file_path: Path to the source file
            
        Returns:
            List of call dicts with caller_id, callee_name, call_type
        """
        calls = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                caller_id = self._get_caller_id(node, file_path, tree)
                callee_name = self._get_callee_name(node)
                
                if caller_id and callee_name:
                    calls.append({
                        'caller_id': caller_id,
                        'callee_name': callee_name,
                        'call_type': 'direct',
                    })
        
        return calls
    
    def _get_caller_id(self, call_node: ast.Call, file_path: str, tree: ast.AST) -> str | None:
        """Get the ID of the function containing this call."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self._node_contains(call_node, node):
                    return f"python://{file_path}::{node.name}"
        return None
    
    def _get_callee_name(self, call_node: ast.Call) -> str | None:
        """Get the name of the called function."""
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            return call_node.func.attr
        return None
    
    def _node_contains(self, inner: ast.AST, outer: ast.AST) -> bool:
        """Check if inner node is contained within outer node."""
        if hasattr(outer, 'body'):
            for child in ast.walk(outer):
                if child is inner:
                    return True
        return False