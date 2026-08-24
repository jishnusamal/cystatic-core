"""TypeScript call index pass - extracts function calls from TypeScript AST."""

from typing import Any

from tree_sitter import Node, Tree

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import CallEntry


def get_node_text(node: Node, source_bytes: bytes) -> str:
    """Helper to extract text from a Tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")


def get_receiver_string(node: Node, source_bytes: bytes) -> str:
    """Recursively convert a receiver node to a dot-separated string."""
    if node.type == "identifier":
        return get_node_text(node, source_bytes)
    elif node.type == "member_expression":
        obj = node.child_by_field_name("object")
        prop = node.child_by_field_name("property")
        if obj and prop:
            val = get_receiver_string(obj, source_bytes)
            attr = get_node_text(prop, source_bytes)
            return f"{val}.{attr}" if val else attr
    return get_node_text(node, source_bytes)


def get_callee_info(node: Node, source_bytes: bytes) -> tuple[str | None, str]:
    """Get callee name and receiver expression string."""
    func_node = node.child_by_field_name("function")
    if not func_node:
        for child in node.children:
            if child.type not in ("arguments", "comment"):
                func_node = child
                break
    if not func_node:
        return None, ""

    if func_node.type == "identifier":
        return get_node_text(func_node, source_bytes), ""
    elif func_node.type == "member_expression":
        obj = func_node.child_by_field_name("object")
        prop = func_node.child_by_field_name("property")
        if prop:
            receiver = get_receiver_string(obj, source_bytes) if obj else ""
            return get_node_text(prop, source_bytes), receiver

    return get_node_text(func_node, source_bytes), ""


def get_caller_info(call_node: Node, source_bytes: bytes) -> tuple[str | None, str]:
    """Get caller function name and optional enclosing class name by traversing parent chain."""
    caller_name = None
    caller_parent = ""

    current = call_node.parent
    while current:
        if current.type in ("function_declaration", "method_definition"):
            name_node = current.child_by_field_name("name")
            if name_node:
                caller_name = get_node_text(name_node, source_bytes)
        elif current.type == "arrow_function":
            p = current.parent
            if p and p.type == "variable_declarator":
                name_node = p.child_by_field_name("name")
                if name_node:
                    caller_name = get_node_text(name_node, source_bytes)
        elif current.type == "class_declaration":
            name_node = current.child_by_field_name("name")
            if name_node:
                caller_parent = get_node_text(name_node, source_bytes)
            break
        current = current.parent

    return caller_name, caller_parent


class TypeScriptCallIndexPass(BaseIndexPass):
    """Index pass that extracts call facts from TypeScript AST.

    Extracts: caller function name, callee name, call type, line.
    """

    def process(self, context: FileContext[Tree], builder: dict[str, Any]) -> None:
        """Extract calls from a TypeScript file context (legacy mode)."""
        tree = context.ast
        source_bytes = context.source.encode("utf-8")

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "call_expression":
                self._add_call(node, context.path, source_bytes, builder)

            stack.extend(reversed(node.children))

    def visit_Call(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle function call node from visitor."""
        source_bytes = context.source.encode("utf-8")
        self._add_call(node, context.path, source_bytes, builder)

    def visit_ClassDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle calls inside class methods by walking the class body."""
        source_bytes = context.source.encode("utf-8")
        stack = [node]
        while stack:
            curr = stack.pop()
            if curr.type == "call_expression":
                self._add_call(curr, context.path, source_bytes, builder)
            stack.extend(reversed(curr.children))

    def _add_call(
        self, node: Node, file_path: str, source_bytes: bytes, builder: dict[str, Any]
    ) -> None:
        """Extract call info and append it to builder."""
        caller_name, caller_parent = get_caller_info(node, source_bytes)
        callee_name, receiver = get_callee_info(node, source_bytes)

        if caller_name and callee_name:
            builder["calls"].append(
                CallEntry(
                    caller=caller_name,
                    callee=callee_name,
                    call_type="direct",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    receiver=receiver,
                    caller_parent=caller_parent,
                )
            )
