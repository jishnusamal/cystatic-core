"""Symbol index — fast lookup from symbol name to AST node.

Purpose:
    Instead of walking the AST repeatedly, every parser gets
    index.lookup("redeem_discount") for O(1) access.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set, Tuple


class SymbolIndex:
    """Index of all symbols in a Python AST.

    Provides fast lookup:
        index.lookup("redeem_discount") -> AST node
        index.lookup_method("Customer.save") -> AST node
        index.get_all_functions() -> list of (name, node)
    """

    def __init__(self) -> None:
        self._functions: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self._methods: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self._classes: Dict[str, ast.ClassDef] = {}
        self._async_functions: Dict[str, ast.AsyncFunctionDef] = {}
        self._decorators: Dict[str, List[ast.expr]] = {}
        self._imports: Dict[str, str] = {}
        self._from_imports: Dict[str, Tuple[str, Optional[str]]] = {}
        self._constants: Dict[str, ast.Assign] = {}
        self._enums: Dict[str, ast.ClassDef] = {}

    def build(self, tree: ast.Module) -> SymbolIndex:
        """Walk the AST and index all symbols."""
        self._walk(tree.body, current_class=None)
        return self

    def _walk(
        self,
        nodes: List[ast.stmt],
        current_class: Optional[str],
    ) -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{current_class}.{node.name}" if current_class else node.name
                if current_class:
                    self._methods[qualified] = node
                else:
                    self._functions[node.name] = node
                if isinstance(node, ast.AsyncFunctionDef):
                    self._async_functions[qualified] = node

                # Index decorators
                if node.decorator_list:
                    self._decorators[qualified] = node.decorator_list

            elif isinstance(node, ast.ClassDef):
                self._classes[node.name] = node
                # Check if it's an enum
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "Enum":
                        self._enums[node.name] = node
                        break
                self._walk(node.body, current_class=node.name)

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self._constants[target.id] = node

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    self._imports[name] = alias.name

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        name = alias.asname or alias.name
                        self._from_imports[name] = (node.module, alias.asname)

    # ------------------------------------------------------------------
    # Lookup methods
    # ------------------------------------------------------------------

    def lookup(self, name: str) -> Optional[ast.AST]:
        """Look up a symbol by name.

        Searches: functions, methods (qualified), classes, constants.
        """
        if name in self._functions:
            return self._functions[name]
        if name in self._methods:
            return self._methods[name]
        if name in self._classes:
            return self._classes[name]
        if name in self._constants:
            return self._constants[name]
        return None

    def lookup_function(self, name: str) -> Optional[ast.FunctionDef | ast.AsyncFunctionDef]:
        """Look up a top-level function by name."""
        return self._functions.get(name)

    def lookup_method(self, qualified_name: str) -> Optional[ast.FunctionDef | ast.AsyncFunctionDef]:
        """Look up a method by qualified name (e.g. 'Customer.save')."""
        return self._methods.get(qualified_name)

    def lookup_class(self, name: str) -> Optional[ast.ClassDef]:
        """Look up a class by name."""
        return self._classes.get(name)

    def lookup_decorators(self, name: str) -> Optional[List[ast.expr]]:
        """Get decorators for a function/method/class."""
        return self._decorators.get(name)

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_all_functions(self) -> List[Tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
        """Get all top-level functions."""
        return list(self._functions.items())

    def get_all_methods(self) -> List[Tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
        """Get all methods (qualified names)."""
        return list(self._methods.items())

    def get_all_classes(self) -> List[Tuple[str, ast.ClassDef]]:
        """Get all classes."""
        return list(self._classes.items())

    def get_all_async_functions(self) -> List[Tuple[str, ast.AsyncFunctionDef]]:
        """Get all async functions/methods."""
        return list(self._async_functions.items())

    def get_all_enums(self) -> List[Tuple[str, ast.ClassDef]]:
        """Get all enum classes."""
        return list(self._enums.items())

    def get_all_constants(self) -> List[Tuple[str, ast.Assign]]:
        """Get all module-level constants."""
        return list(self._constants.items())

    def function_exists(self, name: str) -> bool:
        """Check if a function exists in the index."""
        return name in self._functions or name in self._methods

    def class_exists(self, name: str) -> bool:
        """Check if a class exists in the index."""
        return name in self._classes

    def get_functions_in_class(self, class_name: str) -> List[Tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
        """Get all methods of a class."""
        prefix = f"{class_name}."
        return [
            (name, node) for name, node in self._methods.items()
            if name.startswith(prefix)
        ]

    def get_decorator_names(self, name: str) -> List[str]:
        """Get string names of decorators for a symbol."""
        decorators = self._decorators.get(name, [])
        result: List[str] = []
        for d in decorators:
            if isinstance(d, ast.Name):
                result.append(d.id)
            elif isinstance(d, ast.Attribute):
                result.append(f"{_attr_chain(d)}")
            elif isinstance(d, ast.Call):
                if isinstance(d.func, ast.Name):
                    result.append(d.func.id)
                elif isinstance(d.func, ast.Attribute):
                    result.append(f"{_attr_chain(d.func)}")
        return result

    def resolve_import(self, name: str) -> Optional[str]:
        """Resolve an imported name to its module path."""
        if name in self._from_imports:
            module, alias = self._from_imports[name]
            return module
        if name in self._imports:
            return self._imports[name]
        return None


def _attr_chain(node: ast.Attribute) -> str:
    """Convert an attribute chain like a.b.c to string 'a.b.c'."""
    parts: List[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    return ".".join(parts)