"""TypeScript import index pass - extracts import statements from TypeScript AST."""

from typing import Any

from tree_sitter import Node, Tree

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import ImportEntry


def get_node_text(node: Node, source_bytes: bytes) -> str:
    """Helper to extract text from a Tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")


def extract_import_info(node: Node, source_bytes: bytes) -> tuple[str, list[str], str]:
    """Extract module path, symbols, and import type from an import statement."""
    source_node = node.child_by_field_name("source")
    module_name = ""
    if source_node:
        module_name = get_node_text(source_node, source_bytes).strip("'\"")

    names = []
    import_type = "import"

    clause = node.child_by_field_name("import_clause")
    if clause:
        # Check named imports: { foo, bar }
        named = None
        for child in clause.children:
            if child.type == "named_imports":
                named = child
                break
        if named:
            import_type = "from_import"
            for spec in named.children:
                if spec.type == "import_specifier":
                    name_node = spec.child_by_field_name("name")
                    if name_node:
                        names.append(get_node_text(name_node, source_bytes))
        else:
            # Check namespace import: * as fs
            namespace = None
            for child in clause.children:
                if child.type == "namespace_import":
                    namespace = child
                    break
            if namespace:
                import_type = "import"
                for child in namespace.children:
                    if child.type == "identifier":
                        names.append(get_node_text(child, source_bytes))
                        break
            else:
                # Default import: e.g. import defaultExport from ...
                import_type = "from_import"
                for child in clause.children:
                    if child.type == "identifier":
                        names.append(get_node_text(child, source_bytes))
                        break

    # Side-effect import (e.g. import "./module")
    if not names:
        names = [module_name]

    return module_name, names, import_type


class TypeScriptImportIndexPass(BaseIndexPass):
    """Index pass that extracts import facts from TypeScript AST.

    Extracts: module path, imported names, import type, line number.
    """

    def process(self, context: FileContext[Tree], builder: dict[str, Any]) -> None:
        """Extract imports from a TypeScript file context (legacy mode)."""
        tree = context.ast
        source_bytes = context.source.encode("utf-8")

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "import_statement":
                self._add_import(node, context.path, source_bytes, builder)

            stack.extend(reversed(node.children))

    def visit_Import(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle import statement from visitor."""
        source_bytes = context.source.encode("utf-8")
        self._add_import(node, context.path, source_bytes, builder)

    def _add_import(
        self, node: Node, file_path: str, source_bytes: bytes, builder: dict[str, Any]
    ) -> None:
        """Helper to extract and append import entry."""
        module, names, import_type = extract_import_info(node, source_bytes)
        builder["imports"].append(
            ImportEntry(
                module=module,
                names=tuple(names),
                import_type=import_type,
                file=file_path,
                line=node.start_point[0] + 1,
            )
        )
