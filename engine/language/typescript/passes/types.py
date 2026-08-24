"""TypeScript type index pass - extracts type relationships from TypeScript AST."""

from typing import Any

from tree_sitter import Node, Tree

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import TypeRelationshipEntry


def get_node_text(node: Node, source_bytes: bytes) -> str:
    """Helper to extract text from a Tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")


def get_base_classes(node: Node, source_bytes: bytes) -> list[str]:
    """Extract parent classes from class heritage."""
    bases = []
    heritage = node.child_by_field_name("heritage")
    if not heritage:
        for child in node.children:
            if child.type == "class_heritage":
                heritage = child
                break
    if heritage:
        for child in heritage.children:
            if child.type == "extends_clause":
                for extends_child in child.children:
                    if extends_child.type in ("type_identifier", "member_expression", "identifier"):
                        bases.append(get_node_text(extends_child, source_bytes))
    return bases


class TypeScriptTypeIndexPass(BaseIndexPass):
    """Index pass that extracts type relationship facts from TypeScript AST.

    Extracts: inheritance (extends relation).
    """

    def process(self, context: FileContext[Tree], builder: dict[str, Any]) -> None:
        """Extract type relationships from a TypeScript file context (legacy mode)."""
        tree = context.ast
        source_bytes = context.source.encode("utf-8")

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "class_declaration":
                self._extract_relationships(node, context.path, source_bytes, builder)

            stack.extend(reversed(node.children))

    def visit_ClassDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle class definition node from visitor."""
        source_bytes = context.source.encode("utf-8")
        self._extract_relationships(node, context.path, source_bytes, builder)

    def _extract_relationships(
        self, node: Node, file_path: str, source_bytes: bytes, builder: dict[str, Any]
    ) -> None:
        """Extract relationships and append to builder."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        class_name = get_node_text(name_node, source_bytes)
        bases = get_base_classes(node, source_bytes)
        for base in bases:
            builder["type_relationships"].append(
                TypeRelationshipEntry(
                    source=class_name,
                    target=base,
                    relation_type="extends",
                    file=file_path,
                    line=node.start_point[0] + 1,
                )
            )
