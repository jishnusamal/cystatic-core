"""Python persistence index pass - detects ORM models from Python AST.

Emits only raw persistence facts. No resolution, no symbol matching.
"""

import ast
from typing import Any

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import PersistenceEntry


class PythonPersistenceIndexPass(BaseIndexPass):
    """Index pass that extracts persistence model facts from Python AST.

    Detects ORM/ODM models (SQLAlchemy, Django, Tortoise).
    No semantic inference - just structural model discovery.

    Supports both the visitor pattern (visit_ClassDef) and the traditional
    process() method for backward compatibility.
    """

    # SQLAlchemy base class patterns
    SA_BASES = {"declarative_base", "Base", "Model"}
    DJANGO_BASE = "models.Model"

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract persistence models from a Python file context (legacy mode)."""
        tree = context.ast
        file_path = context.path

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                model = self._extract_model(node, file_path)
                if model:
                    builder["persistence_models"].append(model)

    def visit_ClassDef(self, node: ast.ClassDef, context: FileContext, builder: dict[str, Any]) -> None:
        """Handle class definition node from visitor."""
        model = self._extract_model(node, context.path)
        if model:
            builder["persistence_models"].append(model)

    def _extract_model(self, node: ast.ClassDef, file_path: str) -> PersistenceEntry | None:
        """Extract a persistence model from a class definition."""
        framework = self._detect_framework(node)
        if not framework:
            return None

        table_name = self._extract_table_name(node)

        fields = []
        relationships = []

        for child in node.body:
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        field_info = self._extract_field(target.id, child.value, framework)
                        if field_info:
                            if field_info.get("is_relationship"):
                                relationships.append(field_info)
                            else:
                                fields.append(field_info)

        return PersistenceEntry(
            name=node.name,
            kind="table",
            table_name=table_name,
            framework=framework,
            file=file_path,
            line=node.lineno,
            fields=tuple(fields),
            relationships=tuple(relationships),
        )

    def _detect_framework(self, node: ast.ClassDef) -> str | None:
        """Detect the ORM framework from base classes."""
        for base in node.bases:
            base_str = self._base_to_string(base)
            if base_str == self.DJANGO_BASE:
                return "django"
            if base_str in self.SA_BASES or "Base" in base_str:
                return "sqlalchemy"
            if "Model" in base_str and "tortoise" in base_str.lower():
                return "tortoise"
        return None

    def _base_to_string(self, node: ast.AST) -> str:
        """Convert a base class node to a string representation."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            current: ast.AST = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""

    def _extract_table_name(self, node: ast.ClassDef) -> str:
        """Extract the table/collection name from a model class."""
        for child in node.body:
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id in ("__tablename__", "Meta"):
                        if isinstance(child.value, ast.Constant):
                            return str(child.value.value)
            if isinstance(child, ast.ClassDef) and child.name == "Meta":
                for meta_child in child.body:
                    if isinstance(meta_child, ast.Assign):
                        for target in meta_child.targets:
                            if isinstance(target, ast.Name) and target.id == "db_table":
                                if isinstance(meta_child.value, ast.Constant):
                                    return str(meta_child.value.value)
        return ""

    def _extract_field(self, name: str, value: ast.AST, framework: str) -> dict[str, Any] | None:
        """Extract a field definition from an assignment."""
        field_info: dict[str, Any] = {
            "name": name,
            "field_type": "unknown",
            "is_relationship": False,
            "nullable": False,
            "unique": False,
            "index": False,
        }

        if isinstance(value, ast.Call):
            func_name = self._base_to_string(value.func)
            field_info["field_type"] = func_name

            if "relationship" in func_name.lower() or "ForeignKey" in func_name:
                field_info["is_relationship"] = True
                if value.args:
                    first_arg = value.args[0]
                    if isinstance(first_arg, ast.Constant):
                        field_info["related_model"] = str(first_arg.value)
                    elif isinstance(first_arg, ast.Name):
                        field_info["related_model"] = first_arg.id

            for kw in value.keywords:
                if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                    field_info["nullable"] = bool(kw.value.value)
                elif kw.arg == "unique" and isinstance(kw.value, ast.Constant):
                    field_info["unique"] = bool(kw.value.value)
                elif kw.arg == "index" and isinstance(kw.value, ast.Constant):
                    field_info["index"] = bool(kw.value.value)

        return field_info