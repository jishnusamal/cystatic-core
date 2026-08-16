"""TypeScript composite visitor - walks Tree-sitter AST once and dispatches to all indexing passes."""

import time
from typing import Any
from tree_sitter import Tree, Node

from engine.language.base.file_context import FileContext
from engine.language.base.instrumentation import get_instrumentation
from engine.language.base.visitors import BaseVisitor


class TypeScriptVisitor(BaseVisitor[Tree]):
    """Composite visitor for TypeScript Tree-sitter AST.

    Walks the Tree-sitter AST exactly once per file and dispatches node events
    to all registered indexing passes. Each pass receives the same
    node events but maintains its own independent state in the builder.
    """

    def visit(self, context: FileContext[Tree], builder: dict[str, Any]) -> None:
        """Walk the AST once and dispatch to all registered collectors.

        Args:
            context: FileContext with parsed Tree-sitter Tree
            builder: Mutable builder dict for collected facts
        """
        inst = get_instrumentation()
        tree = context.ast
        root_node = tree.root_node

        # Count AST nodes
        ast_nodes = 0
        stack = [root_node]
        while stack:
            n = stack.pop()
            ast_nodes += 1
            stack.extend(n.children)
            
        inst.increment_counter("Visitor", "ast_nodes_visited", ast_nodes)

        # Dispatch nodes recursively starting from root_node
        self._dispatch(root_node, context, builder)

    def _dispatch(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Dispatch a node to all registered collectors.

        Args:
            node: Node to dispatch
            context: FileContext with parsed Tree
            builder: Mutable builder dict for collected facts
        """
        inst = get_instrumentation()

        node_type = node.type
        if node_type == "function_declaration":
            inst.increment_counter("Visitor", "functions_visited")
            self._visit_FunctionDef(node, context, builder)
        elif node_type == "class_declaration":
            inst.increment_counter("Visitor", "classes_visited")
            self._visit_ClassDef(node, context, builder)
            # Don't recurse into ClassDef - the ClassDef handler extracts methods/fields
            return
        elif node_type == "import_statement":
            inst.increment_counter("Visitor", "imports_visited")
            self._visit_Import(node, context, builder)
        elif node_type == "call_expression":
            inst.increment_counter("Visitor", "calls_visited")
            self._visit_Call(node, context, builder)
        elif node_type == "interface_declaration":
            inst.increment_counter("Visitor", "interfaces_visited")
            self._visit_InterfaceDef(node, context, builder)
        elif node_type == "type_alias_declaration":
            inst.increment_counter("Visitor", "type_aliases_visited")
            self._visit_TypeAliasDef(node, context, builder)
        elif node_type == "enum_declaration":
            inst.increment_counter("Visitor", "enums_visited")
            self._visit_EnumDef(node, context, builder)
        elif node_type == "lexical_declaration":
            inst.increment_counter("Visitor", "variables_visited")
            self._visit_VariableDef(node, context, builder)

        # Recursively walk child nodes for nested structures
        for child in node.children:
            self._dispatch(child, context, builder)

    def _visit_FunctionDef(
        self,
        node: Node,
        context: FileContext[Tree],
        builder: dict[str, Any],
    ) -> None:
        """Dispatch function definition to all collectors."""
        inst = get_instrumentation()

        for collector in self._collectors:
            if hasattr(collector, "visit_FunctionDef"):
                pass_name = type(collector).__name__

                start = time.perf_counter()
                try:
                    collector.visit_FunctionDef(node, context, builder)
                except Exception:
                    pass
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_FunctionDef", elapsed)

    def _visit_ClassDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Dispatch class definition to all collectors."""
        inst = get_instrumentation()

        for collector in self._collectors:
            if hasattr(collector, "visit_ClassDef"):
                pass_name = type(collector).__name__

                start = time.perf_counter()
                try:
                    collector.visit_ClassDef(node, context, builder)
                except Exception:
                    pass
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_ClassDef", elapsed)

    def _visit_Import(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Dispatch import statement to all collectors."""
        inst = get_instrumentation()

        for collector in self._collectors:
            for hook in ("visit_Import", "visit_ImportFrom"):
                if hasattr(collector, hook):
                    pass_name = type(collector).__name__

                    start = time.perf_counter()
                    try:
                        getattr(collector, hook)(node, context, builder)
                    except Exception:
                        pass
                    finally:
                        elapsed = time.perf_counter() - start
                        inst.record_method_time(pass_name, hook, elapsed)

    def _visit_Call(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Dispatch function call to all collectors."""
        inst = get_instrumentation()

        for collector in self._collectors:
            if hasattr(collector, "visit_Call"):
                pass_name = type(collector).__name__

                start = time.perf_counter()
                try:
                    collector.visit_Call(node, context, builder)
                except Exception:
                    pass
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_Call", elapsed)

    def _visit_InterfaceDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Dispatch interface definition to all collectors."""
        inst = get_instrumentation()

        for collector in self._collectors:
            if hasattr(collector, "visit_InterfaceDef"):
                pass_name = type(collector).__name__

                start = time.perf_counter()
                try:
                    collector.visit_InterfaceDef(node, context, builder)
                except Exception:
                    pass
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_InterfaceDef", elapsed)

    def _visit_TypeAliasDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Dispatch type alias definition to all collectors."""
        inst = get_instrumentation()

        for collector in self._collectors:
            if hasattr(collector, "visit_TypeAliasDef"):
                pass_name = type(collector).__name__

                start = time.perf_counter()
                try:
                    collector.visit_TypeAliasDef(node, context, builder)
                except Exception:
                    pass
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_TypeAliasDef", elapsed)

    def _visit_EnumDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Dispatch enum definition to all collectors."""
        inst = get_instrumentation()

        for collector in self._collectors:
            if hasattr(collector, "visit_EnumDef"):
                pass_name = type(collector).__name__

                start = time.perf_counter()
                try:
                    collector.visit_EnumDef(node, context, builder)
                except Exception:
                    pass
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_EnumDef", elapsed)

    def _visit_VariableDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Dispatch variable definition to all collectors."""
        inst = get_instrumentation()

        for collector in self._collectors:
            if hasattr(collector, "visit_VariableDef"):
                pass_name = type(collector).__name__

                start = time.perf_counter()
                try:
                    collector.visit_VariableDef(node, context, builder)
                except Exception:
                    pass
                finally:
                    elapsed = time.perf_counter() - start
                    inst.record_method_time(pass_name, "visit_VariableDef", elapsed)


__all__ = ["TypeScriptVisitor"]
