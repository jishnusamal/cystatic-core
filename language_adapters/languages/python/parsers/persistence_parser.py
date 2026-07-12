"""Persistence parser — extracts ORM model definitions.

Extracts:
    Model, Field, ForeignKey, UniqueConstraint, Index,
    PrimaryKey, Default, Nullability
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    ModelNode,
    FieldNode,
    HasFieldEdge,
    InheritsEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.languages.python.ast.symbol_index import SymbolIndex
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class PersistenceParser(GraphBuilder):
    """Extracts ORM model definitions from Python AST."""

    _DJANGO_MODEL_BASES: Set[str] = {"Model", "models.Model"}
    _SQLALCHEMY_BASES: Set[str] = {"Base", "declarative_base"}

    _FIELD_TYPES: Set[str] = {
        "CharField", "IntegerField", "FloatField", "BooleanField",
        "DateField", "DateTimeField", "TextField", "EmailField",
        "URLField", "FileField", "ImageField", "ForeignKey",
        "OneToOneField", "ManyToManyField", "DecimalField",
        "SlugField", "UUIDField", "JSONField", "BinaryField",
        "PositiveIntegerField", "SmallIntegerField", "BigIntegerField",
        "DurationField", "TimeField", "AutoField", "BigAutoField",
        "SmallAutoField", "GenericIPAddressField",
    }

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self._extract_model(node, graph, file_path)

        return graph

    def _extract_model(
        self,
        class_node: ast.ClassDef,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        name = class_node.name

        # Check if this is an ORM model
        is_model = False
        orm_type = ""
        for base in class_node.bases:
            base_str = ast.unparse(base)
            if base_str in self._DJANGO_MODEL_BASES or "models.Model" in base_str:
                is_model = True
                orm_type = "django"
                break
            if any(sa in base_str for sa in self._SQLALCHEMY_BASES):
                is_model = True
                orm_type = "sqlalchemy"
                break

        if not is_model:
            return

        model = G.ensure_model(
            graph, name, file_path,
            orm=orm_type,
            bases=[ast.unparse(b) for b in class_node.bases],
        )

        # Extract fields
        for child in class_node.body:
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        field_name = target.name

                        # Skip class-level non-field assignments
                        if field_name.startswith("__"):
                            continue
                        if field_name in {"Meta", "objects", "DoesNotExist"}:
                            continue

                        field_type = ""
                        nullable = True
                        has_default = False
                        is_primary_key = False
                        is_unique = False
                        is_indexed = False
                        is_foreign_key = False
                        references = None

                        # Extract field type from the right-hand side
                        if isinstance(child.value, ast.Call):
                            func = child.value.func
                            if isinstance(func, ast.Name):
                                field_type = func.id
                            elif isinstance(func, ast.Attribute):
                                field_type = func.attr

                            # Extract field properties from kwargs
                            for kw in child.value.keywords:
                                if kw.arg == "null" and isinstance(kw.value, ast.Constant):
                                    nullable = bool(kw.value.value)
                                elif kw.arg == "default":
                                    has_default = True
                                elif kw.arg == "primary_key" and isinstance(kw.value, ast.Constant):
                                    is_primary_key = bool(kw.value.value)
                                elif kw.arg == "unique" and isinstance(kw.value, ast.Constant):
                                    is_unique = bool(kw.value.value)
                                elif kw.arg == "db_index" and isinstance(kw.value, ast.Constant):
                                    is_indexed = bool(kw.value.value)

                            # Detect foreign keys
                            if field_type in {"ForeignKey", "OneToOneField"}:
                                is_foreign_key = True
                                if child.value.args:
                                    first_arg = child.value.args[0]
                                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                                        references = first_arg.value

                        field = G.ensure_field(
                            graph, field_name, file_path,
                            model_name=name,
                            field_type=field_type,
                            nullable=nullable,
                            has_default=has_default,
                            is_primary_key=is_primary_key,
                            is_unique=is_unique,
                            is_indexed=is_indexed,
                            is_foreign_key=is_foreign_key,
                            references=references,
                        )
                        graph.add_edge(HasFieldEdge(source=model, target=field))