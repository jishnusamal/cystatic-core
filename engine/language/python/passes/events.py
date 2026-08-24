"""Python event index pass - detects event operations from Python AST.

Emits only raw event facts. No analysis of event flow or handlers.
"""

import ast
from typing import Any, ClassVar

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import EventEntry


class PythonEventIndexPass(BaseIndexPass):
    """Index pass that extracts event operation facts from Python AST.

    Recognizes framework-specific event methods: send, publish, emit, dispatch.
    No event flow analysis — just structural event discovery.

    Supports both the visitor pattern (visit_Call) and the traditional
    process() method for backward compatibility.
    """

    EVENT_METHODS: ClassVar[dict[str, str]] = {
        "send": "send",
        "send_robust": "send",
        "publish": "publish",
        "emit": "emit",
        "dispatch": "dispatch",
        "broadcast": "broadcast",
        "trigger": "dispatch",
        "fire": "emit",
    }

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract event operations from a Python file context (legacy mode)."""
        tree = context.ast
        file_path = context.path

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                event = self._extract_event(node, file_path)
                if event:
                    builder["events"].append(event)

    def visit_Call(
        self, node: ast.Call, context: FileContext, builder: dict[str, Any]
    ) -> None:
        """Handle function call node from visitor."""
        event = self._extract_event(node, context.path)
        if event:
            builder["events"].append(event)

    def _extract_event(self, node: ast.Call, file_path: str) -> EventEntry | None:
        """Extract an event construct from a function call."""
        if not isinstance(node.func, ast.Attribute):
            return None

        method_name = node.func.attr
        if method_name not in self.EVENT_METHODS:
            return None

        operation_kind = self.EVENT_METHODS[method_name]
        event_name = self._extract_event_name(node)
        symbol_name = self._get_enclosing_function_name(node)

        return EventEntry(
            symbol_name=symbol_name or "",
            operation_kind=operation_kind,
            event_name=event_name,
            file=file_path,
            line=node.lineno,
        )

    def _get_enclosing_function_name(self, call_node: ast.Call) -> str | None:
        """Get the name of the function containing this call.

        This performs a local AST walk. No cross-file resolution is attempted.
        """
        for parent in ast.walk(call_node):
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return parent.name
        return None

    def _extract_event_name(self, node: ast.Call) -> str:
        """Extract the event name/type from a call node."""
        if node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return arg.value

        for kw in node.keywords:
            if kw.arg in ("event", "signal", "name", "type") and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)

        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                return node.func.value.id
            elif (
                isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
            ):
                return f"{node.func.value.value.id}.{node.func.value.attr}"

        return ""
