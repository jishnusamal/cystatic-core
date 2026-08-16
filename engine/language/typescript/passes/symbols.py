"""TypeScript symbol index pass - extracts symbols from TypeScript AST."""

from typing import Any
from tree_sitter import Tree, Node

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import SymbolEntry


def get_node_text(node: Node, source_bytes: bytes) -> str:
    """Helper to extract text from a Tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")


def determine_ts_visibility(node: Node, source_bytes: bytes) -> str:
    """Determine accessibility modifier of a class member."""
    for child in node.children:
        if child.type == "accessibility_modifier":
            mod = get_node_text(child, source_bytes)
            if mod in ("public", "private", "protected"):
                return mod
    return "public"


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


class TypeScriptSymbolIndexPass(BaseIndexPass):
    """Index pass that extracts symbol facts from TypeScript AST.

    Extracts: functions, classes, methods, interfaces, type aliases, enums.
    No semantic interpretation.
    """

    def process(self, context: FileContext[Tree], builder: dict[str, Any]) -> None:
        """Extract symbols from a TypeScript file context (legacy mode)."""
        tree = context.ast
        source_bytes = context.source.encode("utf-8")

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "function_declaration":
                builder["symbols"].append(self._extract_function(node, context.path, source_bytes))
            elif node.type == "class_declaration":
                class_sym, method_syms = self._extract_class(node, context.path, source_bytes)
                builder["symbols"].append(class_sym)
                builder["symbols"].extend(method_syms)
            elif node.type == "interface_declaration":
                builder["symbols"].append(self._extract_interface(node, context.path, source_bytes))
            elif node.type == "type_alias_declaration":
                builder["symbols"].append(self._extract_type_alias(node, context.path, source_bytes))
            elif node.type == "enum_declaration":
                builder["symbols"].append(self._extract_enum(node, context.path, source_bytes))
            elif node.type == "lexical_declaration":
                builder["symbols"].extend(self._extract_variables(node, context.path, source_bytes))

            # Recurse children in reverse to preserve order
            for child in reversed(node.children):
                stack.append(child)

    def visit_ClassDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle class definition node from visitor."""
        source_bytes = context.source.encode("utf-8")
        class_sym, method_syms = self._extract_class(node, context.path, source_bytes)
        builder["symbols"].append(class_sym)
        builder["symbols"].extend(method_syms)

    def visit_FunctionDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle function definition node from visitor."""
        source_bytes = context.source.encode("utf-8")
        builder["symbols"].append(self._extract_function(node, context.path, source_bytes))

    def visit_InterfaceDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle interface definition node from visitor."""
        source_bytes = context.source.encode("utf-8")
        builder["symbols"].append(self._extract_interface(node, context.path, source_bytes))

    def visit_TypeAliasDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle type alias definition node from visitor."""
        source_bytes = context.source.encode("utf-8")
        builder["symbols"].append(self._extract_type_alias(node, context.path, source_bytes))

    def visit_EnumDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle enum definition node from visitor."""
        source_bytes = context.source.encode("utf-8")
        builder["symbols"].append(self._extract_enum(node, context.path, source_bytes))

    def visit_VariableDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle variable definition node from visitor."""
        source_bytes = context.source.encode("utf-8")
        builder["symbols"].extend(self._extract_variables(node, context.path, source_bytes))

    def _extract_function(
        self, node: Node, file_path: str, source_bytes: bytes
    ) -> SymbolEntry:
        """Extract a function definition symbol."""
        name_node = node.child_by_field_name("name")
        name = get_node_text(name_node, source_bytes) if name_node else "anonymous"

        return SymbolEntry(
            name=name,
            kind="function",
            file=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            visibility="public",
            properties={},
        )

    def _extract_class(
        self, node: Node, file_path: str, source_bytes: bytes
    ) -> tuple[SymbolEntry, list[SymbolEntry]]:
        """Extract a class definition with its methods."""
        name_node = node.child_by_field_name("name")
        class_name = get_node_text(name_node, source_bytes) if name_node else "AnonymousClass"

        properties = {
            "bases": get_base_classes(node, source_bytes),
        }

        method_symbols = []
        body = node.child_by_field_name("body")
        if not body:
            for child in node.children:
                if child.type == "class_body":
                    body = child
                    break

        if body:
            for child in body.children:
                if child.type == "method_definition":
                    m_name_node = child.child_by_field_name("name")
                    m_name = get_node_text(m_name_node, source_bytes) if m_name_node else "anonymous"

                    method_sym = SymbolEntry(
                        name=m_name,
                        kind="method",
                        file=file_path,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        visibility=determine_ts_visibility(child, source_bytes),
                        parent=class_name,
                        properties={},
                    )
                    method_symbols.append(method_sym)

        class_sym = SymbolEntry(
            name=class_name,
            kind="class",
            file=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            visibility="public",
            properties=properties,
        )
        return class_sym, method_symbols

    def _extract_interface(
        self, node: Node, file_path: str, source_bytes: bytes
    ) -> SymbolEntry:
        """Extract an interface definition symbol."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            for child in node.children:
                if child.type == "type_identifier":
                    name_node = child
                    break
        name = get_node_text(name_node, source_bytes) if name_node else "AnonymousInterface"

        return SymbolEntry(
            name=name,
            kind="interface",
            file=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            visibility="public",
            properties={},
        )

    def _extract_type_alias(
        self, node: Node, file_path: str, source_bytes: bytes
    ) -> SymbolEntry:
        """Extract a type alias definition symbol."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            for child in node.children:
                if child.type == "type_identifier":
                    name_node = child
                    break
        name = get_node_text(name_node, source_bytes) if name_node else "AnonymousType"

        return SymbolEntry(
            name=name,
            kind="interface",
            file=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            visibility="public",
            properties={},
        )

    def _extract_enum(
        self, node: Node, file_path: str, source_bytes: bytes
    ) -> SymbolEntry:
        """Extract an enum definition symbol."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                    break
        name = get_node_text(name_node, source_bytes) if name_node else "AnonymousEnum"

        return SymbolEntry(
            name=name,
            kind="enum",
            file=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            visibility="public",
            properties={},
        )

    def _extract_variables(
        self, node: Node, file_path: str, source_bytes: bytes
    ) -> list[SymbolEntry]:
        """Extract variable declarations from a lexical declaration."""
        symbols = []
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if not name_node:
                    for sub_child in child.children:
                        if sub_child.type == "identifier":
                            name_node = sub_child
                            break
                if name_node:
                    name = get_node_text(name_node, source_bytes)
                    symbols.append(
                        SymbolEntry(
                            name=name,
                            kind="variable",
                            file=file_path,
                            start_line=child.start_point[0] + 1,
                            end_line=child.end_point[0] + 1,
                            visibility="public",
                            properties={},
                        )
                    )
        return symbols
