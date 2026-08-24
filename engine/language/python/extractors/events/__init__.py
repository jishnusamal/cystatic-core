"""Python event extractor - detects event publish, emit, dispatch, and send operations."""

import ast
from typing import Any, ClassVar

from engine.language.base import BaseExtractor


class PythonEventExtractor(BaseExtractor):
    """
    Extracts event operations from Python source files.

    Recognizes framework-specific event patterns:
    - Django signals: foo.send(), foo.send_robust()
    - FastAPI/Starlette: app.add_event_handler()
    - Generic patterns: publish(), emit(), dispatch(), broadcast()
    - Dramatiq: actor.send(), actor.send_with_options()

    Produces a list of dicts with keys: symbol_id, operation_kind, event_name,
    framework, file, line.
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

    FRAMEWORK_PATTERNS: ClassVar[dict[str, set[str]]] = {
        "django": {"django.dispatch", "django.core.signals"},
        "fastapi": {"fastapi"},
        "celery": {"celery"},
        "dramatiq": {"dramatiq"},
        "redis": {"redis"},
        "pypubsub": {"pubsub"},
    }

    def extract(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """
        Extract event operations from a Python AST.

        Args:
            tree: Parsed Python AST
            file_path: Path to the source file

        Returns:
            List of event construct dicts
        """
        events = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                event = self._extract_event(node, file_path)
                if event:
                    events.append(event)

        return events

    def _extract_event(self, node: ast.Call, file_path: str) -> dict[str, Any] | None:
        """Extract an event construct from a function call."""
        caller_id = self._get_caller_id(node)

        if not isinstance(node.func, ast.Attribute):
            return None

        method_name = node.func.attr
        if method_name not in self.EVENT_METHODS:
            return None

        operation_kind = self.EVENT_METHODS[method_name]
        event_name = self._extract_event_name(node)
        framework = self._detect_framework(node)

        return {
            "symbol_id": caller_id or "",
            "operation_kind": operation_kind,
            "event_name": event_name,
            "framework": framework,
            "file": file_path,
            "line": node.lineno,
        }

    def _get_caller_id(self, call_node: ast.Call) -> str | None:
        """Get the enclosing function name for a call node."""
        for parent in ast.walk(call_node):
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(parent):
                    if child is call_node:
                        return (
                            f"python://{getattr(call_node, 'file', '')}::{parent.name}"
                        )
        return None

    def _extract_event_name(self, node: ast.Call) -> str:
        """Extract the event name/type from a call node."""
        # Check for string arguments first
        if node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return arg.value

        # Check for keyword argument 'event' or 'signal'
        for kw in node.keywords:
            if kw.arg in ("event", "signal", "name", "type") and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)

        # Check for attribute access like SomeEvent.send()
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                # The object name could be the event (e.g., order_created.send())
                return node.func.value.id
            elif (
                isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
            ):
                # Chain like signals.order_created.send()
                return f"{node.func.value.value.id}.{node.func.value.attr}"

        return ""

    def _detect_framework(self, node: ast.Call) -> str:
        """Try to detect the event framework from the call context."""
        # Traverse the attribute chain to detect framework
        current = node.func
        while isinstance(current, ast.Attribute):
            current = current.value

        if isinstance(current, ast.Name):
            for framework, patterns in self.FRAMEWORK_PATTERNS.items():
                if current.id.lower() in patterns:
                    return framework

        return ""
