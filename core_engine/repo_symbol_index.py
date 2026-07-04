"""
Repository-wide symbol index for FULL_FILE analysis mode.

In FULL_FILE mode the orchestrator has access to the head SHA, so it can
pre-scan the entire repository and build this index. Analyzers use it to
expand known symbols beyond the diff boundary.

In DIFF_ONLY mode this index is not built — analysis falls back to
diff-only symbol tracking.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field


_HTTP_METHODS: set[str] = {"get", "post", "put", "delete", "patch", "options", "head"}


def _string_arg(call: ast.Call, idx: int) -> str | None:
    """Pull a string literal from a Call's positional args (defensive)."""
    if idx < len(call.args):
        arg = call.args[idx]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def _flask_methods(call: ast.Call) -> list[str]:
    """Extract HTTP methods from a Flask @app.route(methods=[...]) decorator."""
    for kw in call.keywords:
        if kw.arg != "methods":
            continue
        if isinstance(kw.value, (ast.List, ast.Tuple)):
            out: list[str] = []
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    m = elt.value.lower()
                    if m in _HTTP_METHODS:
                        out.append(m.upper())
            return out
    return []


def _extract_endpoints_from_ast(tree: ast.AST, file_path: str) -> list[dict]:
    """Lightweight FastAPI/Flask route extractor (defensive — no side effects)."""
    endpoints: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            attr = dec.func.attr
            if attr.lower() in _HTTP_METHODS:
                route = _string_arg(dec, 0)
                if route:
                    endpoints.append({
                        "file": file_path,
                        "function": node.name,
                        "method": attr.upper(),
                        "route": route,
                    })
            elif attr == "route":
                route = _string_arg(dec, 0)
                if route:
                    methods = _flask_methods(dec)
                    endpoints.append({
                        "file": file_path,
                        "function": node.name,
                        "method": ",".join(methods) if methods else "GET",
                        "route": route,
                    })
    return endpoints


def _function_names_from_ast(tree: ast.AST) -> set[str]:
    """Collect all function/method names defined in a parsed module."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            names.add(node.name)
    return names


@dataclass
class RepositorySymbolIndex:
    """Repository-wide symbol index built from full file snapshots."""
    known_symbols: set[str] = field(default_factory=set)
    all_endpoints: list[dict] = field(default_factory=list)
    file_symbols: dict[str, set[str]] = field(default_factory=dict)
    file_endpoints: dict[str, list[dict]] = field(default_factory=dict)

    @classmethod
    def from_files(cls, files: list[tuple[str, str]]) -> RepositorySymbolIndex:
        """Build the index from a list of (file_path, content) pairs."""
        idx = cls()
        for file_path, content in files:
            if not file_path or not isinstance(content, str):
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                idx.file_symbols[file_path] = set()
                continue

            symbols = _function_names_from_ast(tree)
            idx.file_symbols[file_path] = symbols
            idx.known_symbols.update(symbols)

            endpoints = _extract_endpoints_from_ast(tree, file_path)
            if endpoints:
                idx.all_endpoints.extend(endpoints)
                idx.file_endpoints[file_path] = endpoints

        return idx

    def is_known(self, symbol: str) -> bool:
        return symbol in self.known_symbols

    def get_endpoints_for_symbol(self, symbol: str) -> list[dict]:
        return [
            ep for ep in self.all_endpoints
            if ep.get("function") == symbol
        ]

    def merge(self, other: RepositorySymbolIndex) -> RepositorySymbolIndex:
        """Merge another index into this one. Returns self for chaining."""
        if other is None:
            return self
        self.known_symbols |= other.known_symbols
        self.all_endpoints.extend(other.all_endpoints)
        for fp, syms in other.file_symbols.items():
            self.file_symbols.setdefault(fp, set()).update(syms)
        for fp, eps in other.file_endpoints.items():
            self.file_endpoints.setdefault(fp, []).extend(eps)
        return self

    def stats(self) -> dict:
        return {
            "known_symbol_count": len(self.known_symbols),
            "endpoint_count": len(self.all_endpoints),
            "indexed_file_count": len(self.file_symbols),
        }
