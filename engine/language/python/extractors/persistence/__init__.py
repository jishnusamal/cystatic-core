"""Python persistence extractor - detects ORM models and repository methods."""

import ast
from typing import Any, ClassVar

from engine.language.base import BaseExtractor


class PythonPersistenceExtractor(BaseExtractor):
    """
    Extracts ORM/ODM persistence constructs from Python source files.

    Recognizes:
    - SQLAlchemy models (declarative base, mapped_column, relationship)
    - Django ORM models (models.Model, fields)
    - Tortoise ORM models
    - Repository methods (CRUD operations)

    Produces a list of dicts with keys: type, symbol_id, name, table_name,
    framework, fields, relationships.
    """

    # SQLAlchemy base class patterns
    SA_BASES: ClassVar[set[str]] = {"declarative_base", "Base", "Model"}

    # Django base class patterns
    DJANGO_BASE = "models.Model"

    def extract(self, tree: ast.AST, file_path: str) -> list[dict[str, Any]]:
        """
        Extract persistence constructs from a Python AST.

        Args:
            tree: Parsed Python AST
            file_path: Path to the source file

        Returns:
            List of persistence construct dicts
        """
        constructs = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                model = self._extract_model(node, file_path)
                if model:
                    constructs.append(model)

        return constructs

    def _extract_model(
        self, node: ast.ClassDef, file_path: str
    ) -> dict[str, Any] | None:
        """Extract a persistence model from a class definition."""
        framework = self._detect_framework(node)
        if not framework:
            return None

        symbol_id = f"python://{file_path}#{node.name}"
        table_name = self._extract_table_name(node)

        fields = []
        relationships = []

        for child in node.body:
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        field_info = self._extract_field(
                            target.id, child.value, framework
                        )
                        if field_info:
                            if field_info.get("is_relationship"):
                                relationships.append(field_info)
                            else:
                                fields.append(field_info)

        return {
            "type": "persistence_model",
            "symbol_id": symbol_id,
            "name": node.name,
            "table_name": table_name,
            "framework": framework,
            "fields": fields,
            "relationships": relationships,
        }

    def _detect_framework(self, node: ast.ClassDef) -> str | None:
        """Detect the ORM framework from base classes."""
        for base in node.bases:
            base_str = self._base_to_string(base)
            if base_str == self.DJANGO_BASE:
                return "django"
            if base_str in self.SA_BASES or "Base" in base_str:
                return "sqlalchemy"
            # Tortoise ORM
            if "Model" in base_str and "tortoise" in base_str.lower():
                return "tortoise"
        return None

    def _base_to_string(self, node: ast.AST) -> str:
        """Convert a base class node to a string representation."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            current = node
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
            if (
                isinstance(child, ast.Assign)
                and isinstance(child.value, ast.Constant)
            ):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id in (
                        "__tablename__",
                        "Meta",
                    ):
                        return str(child.value.value)
            # Django Meta class
            if isinstance(child, ast.ClassDef) and child.name == "Meta":
                for meta_child in child.body:
                    if (
                        isinstance(meta_child, ast.Assign)
                        and isinstance(meta_child.value, ast.Constant)
                    ):
                        for target in meta_child.targets:
                            if isinstance(target, ast.Name) and target.id == "db_table":
                                return str(meta_child.value.value)
        return ""

    def _extract_field(
        self, name: str, value: ast.AST, framework: str
    ) -> dict[str, Any] | None:
        """Extract a field definition from an assignment."""
        field_info = {
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

            # Detect relationship fields
            if "relationship" in func_name.lower() or "ForeignKey" in func_name:
                field_info["is_relationship"] = True
                # Extract the related model from ForeignKey/relationship args
                if value.args:
                    first_arg = value.args[0]
                    if isinstance(first_arg, ast.Constant):
                        field_info["related_model"] = str(first_arg.value)
                    elif isinstance(first_arg, ast.Name):
                        field_info["related_model"] = first_arg.id

            # Extract keyword arguments
            for kw in value.keywords:
                if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                    field_info["nullable"] = bool(kw.value.value)
                elif kw.arg == "unique" and isinstance(kw.value, ast.Constant):
                    field_info["unique"] = bool(kw.value.value)
                elif kw.arg == "index" and isinstance(kw.value, ast.Constant):
                    field_info["index"] = bool(kw.value.value)

        return field_info
