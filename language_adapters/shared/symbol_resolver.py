"""Symbol resolution utilities — resolves dotted names to fully-qualified symbols."""

from __future__ import annotations

import ast
from typing import Dict, List, Optional, Set, Tuple


class SymbolResolver:
    """Resolves symbol references (e.g. foo.bar() -> fully qualified name).

    Useful for both Python and TypeScript adapters.
    """

    def __init__(self) -> None:
        self._imports: Dict[str, str] = {}  # alias -> module
        self._from_imports: Dict[str, Tuple[str, Optional[str]]] = {}  # name -> (module, alias)

    def reset(self) -> None:
        """Clear cached import information."""
        self._imports.clear()
        self._from_imports.clear()

    def extract_imports(self, tree: ast.Module) -> None:
        """Walk an AST and extract all import statements."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    self._imports[name] = alias.name

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        name = alias.asname or alias.name
                        self._from_imports[name] = (node.module, alias.asname)

    def resolve(self, name: str, current_module: Optional[str] = None) -> str:
        """Resolve a potentially dotted name to a fully-qualified symbol.

        Args:
            name: The name to resolve (e.g. 'customer.save', 'redeem_discount').
            current_module: The current module path (e.g. 'payments.views').

        Returns:
            Fully qualified symbol string.
        """
        # Get the base name (before any dots)
        base = name.split(".")[0] if "." in name else name

        # Check if it's a direct import
        if base in self._from_imports:
            module, alias = self._from_imports[base]
            suffix = name[len(base):] if name.startswith(base) and len(name) > len(base) else ""
            return f"{module}.{suffix}" if suffix else module

        # Check if it's a module import
        if base in self._imports:
            module = self._imports[base]
            suffix = name[len(base):] if name.startswith(base) and len(name) > len(base) else ""
            return f"{module}{suffix}"

        # Check if it looks like a method on a class — try to qualify
        if "." in name:
            parts = name.split(".")
            # Maybe the first part is a local variable, resolve later
            return name

        # Otherwise, it's likely a local symbol in the current module
        if current_module:
            return f"{current_module}.{name}"

        return name

    def resolve_call(
        self,
        call_expr: ast.Call,
        current_module: Optional[str] = None,
    ) -> str:
        """Resolve an ast.Call node to a fully-qualified function name.

        Handles:
            foo()                    -> module.foo
            obj.method()             -> module.obj.method
            self.method()            -> module.ClassName.method
            cls.method()             -> module.ClassName.method
            module.function()        -> module.function
            SomeClass.method()       -> module.SomeClass.method
        """
        func = call_expr.func

        if isinstance(func, ast.Name):
            return self.resolve(func.id, current_module)

        if isinstance(func, ast.Attribute):
            # Walk the chain
            parts: List[str] = []
            current = func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value

            if isinstance(current, ast.Name):
                parts.append(current.id)
            elif isinstance(current, ast.Call):
                # Handle chained calls
                parts.append("<call>")

            parts.reverse()
            dotted = ".".join(parts)
            return self.resolve(dotted, current_module)

        return "<unknown>"