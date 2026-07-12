"""AST diff computation — compares old and new ASTs for a changed file.

Detects:
    - body changed
    - signature changed
    - decorator changed
    - parameter added / removed
    - return type changed
    - inheritance changed
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple


class ASTChangeType(Enum):
    BODY_CHANGED = auto()
    SIGNATURE_CHANGED = auto()
    DECORATOR_CHANGED = auto()
    PARAMETER_ADDED = auto()
    PARAMETER_REMOVED = auto()
    RETURN_TYPE_CHANGED = auto()
    INHERITANCE_CHANGED = auto()
    NODE_ADDED = auto()
    NODE_REMOVED = auto()
    VISIBILITY_CHANGED = auto()


@dataclass
class ASTChange:
    """Represents a single change detected between two ASTs."""

    change_type: ASTChangeType
    node_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class ASTDiff:
    """Computes semantic diffs between old and new ASTs."""

    @staticmethod
    def diff(old_content: str, new_content: str) -> List[ASTChange]:
        """Compare old and new Python source and return AST-level changes.

        Args:
            old_content: The old (pre-change) source code.
            new_content: The new (post-change) source code.

        Returns:
            List of ASTChange objects describing semantic differences.
        """
        old_tree = _parse_safe(old_content)
        new_tree = _parse_safe(new_content)

        if old_tree is None and new_tree is None:
            return []
        if old_tree is None:
            return [ASTChange(ASTChangeType.NODE_ADDED, "<file>", new_value="entire file")]
        if new_tree is None:
            return [ASTChange(ASTChangeType.NODE_REMOVED, "<file>", old_value="entire file")]

        changes: List[ASTChange] = []

        old_index = _build_index(old_tree)
        new_index = _build_index(new_tree)

        # Find modified / removed nodes
        for key, old_node in old_index.items():
            if key in new_index:
                new_node = new_index[key]
                changes.extend(ASTDiff._compare_nodes(old_node, new_node))
            else:
                changes.append(
                    ASTChange(
                        ASTChangeType.NODE_REMOVED,
                        key,
                        old_value=_node_summary(old_node),
                    )
                )

        # Find added nodes
        for key, new_node in new_index.items():
            if key not in old_index:
                changes.append(
                    ASTChange(
                        ASTChangeType.NODE_ADDED,
                        key,
                        new_value=_node_summary(new_node),
                    )
                )

        return changes

    @staticmethod
    def _compare_nodes(old: ast.AST, new: ast.AST) -> List[ASTChange]:
        """Compare two AST nodes of the same type and return changes."""
        changes: List[ASTChange] = []

        if isinstance(old, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = old.name

            # Decorator changes
            old_decorators = {_decorator_name(d) for d in old.decorator_list}
            new_decorators = {_decorator_name(d) for d in new.decorator_list}
            added = new_decorators - old_decorators
            removed = old_decorators - new_decorators
            if added or removed:
                changes.append(
                    ASTChange(
                        ASTChangeType.DECORATOR_CHANGED,
                        name,
                        old_value=",".join(sorted(removed)) if removed else None,
                        new_value=",".join(sorted(added)) if added else None,
                        details={"added": list(added), "removed": list(removed)},
                    )
                )

            # Parameter changes
            old_params = {arg.arg for arg in old.args.args}
            new_params = {arg.arg for arg in new.args.args}
            params_added = new_params - old_params
            params_removed = old_params - new_params
            if params_added:
                changes.append(
                    ASTChange(
                        ASTChangeType.PARAMETER_ADDED,
                        name,
                        new_value=",".join(sorted(params_added)),
                        details={"params": list(params_added)},
                    )
                )
            if params_removed:
                changes.append(
                    ASTChange(
                        ASTChangeType.PARAMETER_REMOVED,
                        name,
                        old_value=",".join(sorted(params_removed)),
                        details={"params": list(params_removed)},
                    )
                )

            # Return type changes
            old_return = _annotation_name(old.returns) if old.returns else None
            new_return = _annotation_name(new.returns) if new.returns else None
            if old_return != new_return:
                changes.append(
                    ASTChange(
                        ASTChangeType.RETURN_TYPE_CHANGED,
                        name,
                        old_value=old_return,
                        new_value=new_return,
                    )
                )

            # Body changes (heuristic: different line ranges)
            old_body_range = (
                getattr(old, "lineno", 0),
                getattr(old, "end_lineno", 0),
            )
            new_body_range = (
                getattr(new, "lineno", 0),
                getattr(new, "end_lineno", 0),
            )
            if old_body_range != new_body_range:
                changes.append(
                    ASTChange(
                        ASTChangeType.BODY_CHANGED,
                        name,
                        old_value=f"lines {old_body_range[0]}-{old_body_range[1]}",
                        new_value=f"lines {new_body_range[0]}-{new_body_range[1]}",
                    )
                )

        elif isinstance(old, ast.ClassDef):
            name = old.name

            # Inheritance changes
            old_bases = {_annotation_name(b) for b in old.bases}
            new_bases = {_annotation_name(b) for b in new.bases}
            if old_bases != new_bases:
                changes.append(
                    ASTChange(
                        ASTChangeType.INHERITANCE_CHANGED,
                        name,
                        old_value=",".join(sorted(old_bases)) if old_bases else None,
                        new_value=",".join(sorted(new_bases)) if new_bases else None,
                        details={"old_bases": list(old_bases), "new_bases": list(new_bases)},
                    )
                )

            # Decorator changes on classes
            old_decorators = {_decorator_name(d) for d in old.decorator_list}
            new_decorators = {_decorator_name(d) for d in new.decorator_list}
            added = new_decorators - old_decorators
            removed = old_decorators - new_decorators
            if added or removed:
                changes.append(
                    ASTChange(
                        ASTChangeType.DECORATOR_CHANGED,
                        name,
                        old_value=",".join(sorted(removed)) if removed else None,
                        new_value=",".join(sorted(added)) if added else None,
                        details={"added": list(added), "removed": list(removed)},
                    )
                )

        return changes


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _parse_safe(content: str) -> Optional[ast.Module]:
    try:
        return ast.parse(content)
    except SyntaxError:
        return None


def _build_index(tree: ast.Module) -> Dict[str, ast.AST]:
    """Build a name -> node index for top-level functions and classes."""
    index: Dict[str, ast.AST] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            index[node.name] = node
    return index


def _decorator_name(node: ast.expr) -> str:
    """Extract a string name from a decorator node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_decorator_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return "<complex>"


def _annotation_name(node: Optional[ast.expr]) -> Optional[str]:
    """Extract a string name from a type annotation node."""
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_annotation_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Subscript):
        return f"{_annotation_name(node.value)}[{_annotation_name(node.slice)}]"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return "<complex>"


def _node_summary(node: ast.AST) -> str:
    """Get a short summary of a node."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"def {node.name}(...)"
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}(...)"
    return str(type(node).__name__)