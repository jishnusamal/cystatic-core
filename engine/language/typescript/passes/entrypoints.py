"""TypeScript entrypoint index pass - detects REST API endpoints from TypeScript AST."""

from typing import Any
from tree_sitter import Tree, Node

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import EntrypointEntry

HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch"})


def get_node_text(node: Node, source_bytes: bytes) -> str:
    """Helper to extract text from a Tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")


class TypeScriptEntrypointIndexPass(BaseIndexPass):
    """Index pass that extracts entrypoint facts from TypeScript AST.

    Detects:
    1. Express/Fastify router calls: app.get('/users', getUsers)
    2. NestJS decorators: @Get('/users')
    """

    def process(self, context: FileContext[Tree], builder: dict[str, Any]) -> None:
        """Extract entrypoints from a TypeScript file context (legacy mode)."""
        source_bytes = context.source.encode("utf-8")
        self._process_container(context.ast.root_node, context.path, source_bytes, builder)

    def visit_Call(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle function call node from visitor."""
        source_bytes = context.source.encode("utf-8")
        self._check_express_call(node, context.path, source_bytes, builder)

    def visit_ClassDef(
        self, node: Node, context: FileContext[Tree], builder: dict[str, Any]
    ) -> None:
        """Handle class definition node from visitor."""
        source_bytes = context.source.encode("utf-8")
        body = node.child_by_field_name("body")
        if not body:
            for child in node.children:
                if child.type == "class_body":
                    body = child
                    break
        if body:
            self._process_container(body, context.path, source_bytes, builder)

    def _process_container(
        self, parent_node: Node, file_path: str, source_bytes: bytes, builder: dict[str, Any]
    ) -> None:
        """Recursively process container children, tracking sibling decorators."""
        active_decorators = []
        for child in parent_node.children:
            if child.type == "decorator":
                active_decorators.append(child)
            elif child.type in ("method_definition", "function_declaration"):
                for dec in active_decorators:
                    self._check_decorator_entrypoint(dec, child, file_path, source_bytes, builder)
                active_decorators = []
                self._process_container(child, file_path, source_bytes, builder)
            elif child.type == "call_expression":
                self._check_express_call(child, file_path, source_bytes, builder)
                self._process_container(child, file_path, source_bytes, builder)
            else:
                if child.type not in (";", "comment"):
                    active_decorators = []
                self._process_container(child, file_path, source_bytes, builder)

    def _check_express_call(
        self, node: Node, file_path: str, source_bytes: bytes, builder: dict[str, Any]
    ) -> None:
        """Check for Express/Fastify router call definitions."""
        func = node.child_by_field_name("function")
        if func and func.type == "member_expression":
            prop = func.child_by_field_name("property")
            if prop:
                method = get_node_text(prop, source_bytes).lower()
                if method in HTTP_METHODS:
                    args = node.child_by_field_name("arguments")
                    if args:
                        named_args = [c for c in args.children if c.is_named]
                        if named_args and len(named_args) >= 2:
                            if named_args[0].type == "string":
                                route = get_node_text(named_args[0], source_bytes).strip("'\"")
                                handler_node = named_args[1]
                                if handler_node.type == "identifier":
                                    handler_name = get_node_text(handler_node, source_bytes)
                                else:
                                    handler_name = "anonymous"

                                builder["entrypoints"].append(
                                    EntrypointEntry(
                                        route=f"{method.upper()} {route}",
                                        handler=handler_name,
                                        kind="rest_endpoint",
                                        file=file_path,
                                        line=node.start_point[0] + 1,
                                    )
                                )

    def _check_decorator_entrypoint(
        self, decorator_node: Node, target_node: Node, file_path: str, source_bytes: bytes, builder: dict[str, Any]
    ) -> None:
        """Extract entrypoint from a decorator and associate it with a handler function/method."""
        dec_child = None
        for sub in decorator_node.children:
            if sub.type in ("call_expression", "identifier"):
                dec_child = sub
                break
        if dec_child:
            dec_name = ""
            route = "/"
            if dec_child.type == "identifier":
                dec_name = get_node_text(dec_child, source_bytes)
            elif dec_child.type == "call_expression":
                func = dec_child.child_by_field_name("function")
                if func:
                    dec_name = get_node_text(func, source_bytes)
                args = dec_child.child_by_field_name("arguments")
                if args:
                    named_args = [c for c in args.children if c.is_named]
                    if named_args and named_args[0].type == "string":
                        route = get_node_text(named_args[0], source_bytes).strip("'\"")

            dec_name_lower = dec_name.lower()
            if dec_name_lower in HTTP_METHODS:
                method_name = ""
                name_node = target_node.child_by_field_name("name")
                if name_node:
                    method_name = get_node_text(name_node, source_bytes)

                builder["entrypoints"].append(
                    EntrypointEntry(
                        route=f"{dec_name_lower.upper()} {route}",
                        handler=method_name,
                        kind="rest_endpoint",
                        file=file_path,
                        line=target_node.start_point[0] + 1,
                    )
                )
