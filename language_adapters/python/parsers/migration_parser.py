"""Migration parser — understands Django migrations.

Extracts:
    table, column, nullable, index, default, foreign key,
    rename, backfill, RunPython, RunSQL
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional

from language_adapters.ir import (
    SemanticGraph,
    NodeType,
    MigrationNode,
    TableNode,
    ColumnNode,
    MigratesEdge,
    UsesEdge,
)
from language_adapters.interfaces.graph import GraphBuilder
from language_adapters.shared.graph_builder import GraphBuilderUtils as G


class MigrationParser(GraphBuilder):
    """Extracts database migration operations from Django migration files."""

    _MIGRATION_OPERATIONS: Dict[str, str] = {
        "CreateModel": "create_table",
        "DeleteModel": "drop_table",
        "RenameModel": "rename_table",
        "AlterModelTable": "alter_table",
        "AlterModelOptions": "alter_options",
        "AddField": "add_column",
        "RemoveField": "drop_column",
        "AlterField": "alter_column",
        "RenameField": "rename_column",
        "AddIndex": "add_index",
        "RemoveIndex": "drop_index",
        "AddConstraint": "add_constraint",
        "RemoveConstraint": "drop_constraint",
        "AlterUniqueTogether": "alter_unique",
        "AlterIndexTogether": "alter_index",
        "RunPython": "run_python",
        "RunSQL": "run_sql",
        "SeparateDatabaseAndState": "separate",
    }

    def build(self, graph: SemanticGraph, context: Dict[str, Any]) -> SemanticGraph:
        tree: Optional[ast.Module] = context.get("tree")
        file_path: str = context.get("file_path", "")

        if tree is None:
            return graph

        # Only process migration files
        if "/migrations/" not in file_path and not file_path.endswith("_migration.py"):
            return graph

        self._extract_migrations(tree, graph, file_path)

        return graph

    def _extract_migrations(
        self,
        tree: ast.Module,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        migration = MigrationNode(
            name=file_path.split("/")[-1].replace(".py", ""),
            file_path=file_path,
        )
        graph.add_node(migration)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "operations":
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Call):
                                    self._process_operation(
                                        elt, migration, graph, file_path
                                    )

    def _process_operation(
        self,
        call: ast.Call,
        migration: MigrationNode,
        graph: SemanticGraph,
        file_path: str,
    ) -> None:
        func = call.func
        if not isinstance(func, ast.Name):
            return

        op_name = func.id
        op_type = self._MIGRATION_OPERATIONS.get(op_name)

        if op_type is None:
            return

        # Extract model/table name from first argument
        model_name = None
        if call.args:
            first_arg = call.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                model_name = first_arg.value

        # Extract field name for field operations
        field_name = None
        if op_type in ("add_column", "drop_column", "alter_column", "rename_column"):
            if len(call.args) > 1:
                second_arg = call.args[1]
                if isinstance(second_arg, ast.Constant) and isinstance(second_arg.value, str):
                    field_name = second_arg.value

        # Extract keyword arguments
        kwargs: Dict[str, Any] = {}
        for kw in call.keywords:
            if kw.arg and isinstance(kw.value, ast.Constant):
                kwargs[kw.arg] = kw.value.value

        # Create operation record
        operation = {
            "type": op_type,
            "operation": op_name,
            "model": model_name,
            "field": field_name,
            "kwargs": kwargs,
        }
        migration.operations.append(operation)

        # Create table/column nodes and edges
        if model_name:
            table = TableNode(
                name=model_name,
                file_path=file_path,
            )
            graph.add_node(table)
            graph.add_edge(
                MigratesEdge(
                    source=migration,
                    target=table,
                    operation=op_type,
                )
            )

        if field_name and model_name:
            column = ColumnNode(
                name=field_name,
                file_path=file_path,
                table_name=model_name,
                column_type=kwargs.get("field", ""),
                nullable=kwargs.get("null", True),
                has_default="default" in kwargs,
                is_primary_key=kwargs.get("primary_key", False),
                is_unique=kwargs.get("unique", False),
                is_indexed=kwargs.get("db_index", False),
            )
            graph.add_node(column)
            graph.add_edge(
                MigratesEdge(
                    source=migration,
                    target=column,
                    operation=op_type,
                )
            )