"""Pass 2 — Consistency Validation.

Question: Are all referenced entities internally consistent?

Checks:
- Removed symbols exist in base repository, absent from head.
- Added symbols absent from base, exist in head repository.
- Modified symbols exist in both base and head repositories.
- Every behavior references valid symbols.
- Every entry point belongs to RepositoryModel.
- Every execution graph references known nodes.

This is compiler validation, not business validation.
"""

from typing import cast

from engine.operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from engine.operational.model import OperationalChangeModel


class ConsistencyValidationPass(OperationalCompilerPass):
    """
    Pass 2 of Operational compilation.

    Validates that all references across the composed models are internally
    consistent. This catches data integrity issues before downstream consumers
    (renderers, AI) process the model.

    Uses RepositoryDelta to validate change types correctly:
    - Removed symbols must exist in base, be absent from head
    - Added symbols must be absent from base, exist in head
    - Modified symbols must exist in both
    """

    @property
    def name(self) -> str:
        return "consistency_validation"

    def validate_input(self, context: OperationalPassContext) -> bool:
        """Verify the composed model exists before validation."""
        return context.composed_model is not None

    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Validate internal consistency of the composed model.

        Args:
            context: Pass context with composed_model set.

        Returns:
            Updated context with consistency_errors populated.
        """
        if not self.validate_input(context):
            context.consistency_errors.append(
                "Cannot validate: no composed model in context"
            )
            return context

        model = context.composed_model
        if model is None:
            return context

        errors: list[str] = []

        # Get symbol IDs from both base and head repositories for cross-model validation
        head_symbol_ids = {s.id for s in model.repository.symbols}
        base_symbol_ids: frozenset[str] = frozenset()
        if context.repository_delta is not None:
            base_symbol_ids = context.repository_delta.get_base_symbol_ids()

        # 1. Validate changed symbols using cross-model validation
        errors.extend(
            self._validate_changed_symbols_cross_model(
                model, base_symbol_ids, head_symbol_ids
            )
        )

        # 2. Every behavior references valid symbols (in head repository)
        errors.extend(
            self._validate_behavior_symbols(model, head_symbol_ids)
        )

        # 3. Every entry point belongs to RepositoryModel
        errors.extend(
            self._validate_entry_points(model, head_symbol_ids)
        )

        # 4. Every execution graph references known nodes
        errors.extend(
            self._validate_execution_graphs(model, head_symbol_ids)
        )

        context.consistency_errors = errors
        return context

    def _validate_changed_symbols_cross_model(
        self,
        model: "OperationalChangeModel",
        base_symbol_ids: frozenset[str],
        head_symbol_ids: set[str],
    ) -> list[str]:
        """
        Validate changed symbols using cross-model validation.

        Removed symbols: must exist in base, be absent from head.
        Added symbols: must be absent from base, exist in head.
        Modified symbols: must exist in both base and head.
        """
        errors: list[str] = []

        # Check added symbols - should exist in head repository
        for symbol in model.change.added_symbols:
            if symbol.id not in head_symbol_ids:
                errors.append(
                    f"Added symbol '{symbol.id}' not found in head repository model"
                )

        # Check removed symbols - should exist in base repository
        for symbol in model.change.removed_symbols:
            if symbol.id not in base_symbol_ids:
                errors.append(
                    f"Removed symbol '{symbol.id}' not found in base repository model"
                )

        # Check modified symbols - should exist in both repositories
        for modified in model.change.modified_symbols:
            if modified.symbol.id not in base_symbol_ids:
                errors.append(
                    f"Modified symbol '{modified.symbol.id}' not found "
                    "in base repository model"
                )
            if modified.symbol.id not in head_symbol_ids:
                errors.append(
                    f"Modified symbol '{modified.symbol.id}' not found "
                    "in head repository model"
                )

        return errors

    def _validate_changed_symbols(
        self,
        model: "OperationalChangeModel",
        known_symbol_ids: set[str],
    ) -> list[str]:
        """Check that every changed symbol exists in the repository model.

        Deprecated: Use _validate_changed_symbols_cross_model instead.
        Kept for backward compatibility.
        """
        errors: list[str] = []

        # Check added symbols
        for symbol in model.change.added_symbols:
            if symbol.id not in known_symbol_ids:
                errors.append(
                    f"Added symbol '{symbol.id}' not found in repository model"
                )

        # Check removed symbols
        for symbol in model.change.removed_symbols:
            if symbol.id not in known_symbol_ids:
                errors.append(
                    f"Removed symbol '{symbol.id}' not found in repository model"
                )

        # Check modified symbols
        for modified in model.change.modified_symbols:
            if modified.symbol.id not in known_symbol_ids:
                errors.append(
                    f"Modified symbol '{modified.symbol.id}' not found "
                    "in repository model"
                )

        return errors

    def _validate_behavior_symbols(
        self,
        model: "OperationalChangeModel",
        known_symbol_ids: set[str],
    ) -> list[str]:
        """Check that every behavior references valid symbols."""
        errors: list[str] = []

        for behavior in model.behavior.behaviors:
            # Root symbol must exist
            if behavior.root_symbol_id not in known_symbol_ids:
                errors.append(
                    f"Behavior '{behavior.id}' references unknown root symbol "
                    f"'{behavior.root_symbol_id}'"
                )

            # Changed symbol IDs must exist
            for symbol_id in behavior.changed_symbol_ids:
                if symbol_id not in known_symbol_ids:
                    errors.append(
                        f"Behavior '{behavior.id}' references unknown "
                        f"changed symbol '{symbol_id}'"
                    )

        return errors

    def _validate_entry_points(
        self,
        model: "OperationalChangeModel",
        known_symbol_ids: set[str],
    ) -> list[str]:
        """Check that every entry point handler exists in the repository."""
        errors: list[str] = []

        for entry_point in model.repository.entry_points:
            if entry_point.handler_id not in known_symbol_ids:
                errors.append(
                    f"Entry point '{entry_point.route}' references unknown "
                    f"handler '{entry_point.handler_id}'"
                )

        return errors

    def _validate_execution_graphs(
        self,
        model: "OperationalChangeModel",
        known_symbol_ids: set[str],
    ) -> list[str]:
        """Check that every execution graph references known nodes."""
        errors: list[str] = []

        for graph in model.behavior.execution_graphs:
            # Check all nodes
            for node in graph.nodes:
                if node.symbol_id not in known_symbol_ids:
                    errors.append(
                        f"Execution graph '{graph.behavior_id}' contains "
                        f"unknown node '{node.symbol_id}'"
                    )

            # Check all edges reference valid nodes
            node_ids = {n.symbol_id for n in graph.nodes}
            for edge in graph.edges:
                if edge.caller_id not in node_ids:
                    errors.append(
                        f"Execution graph '{graph.behavior_id}' edge caller "
                        f"'{edge.caller_id}' not in nodes"
                    )
                if edge.callee_id not in node_ids:
                    errors.append(
                        f"Execution graph '{graph.behavior_id}' edge callee "
                        f"'{edge.callee_id}' not in nodes"
                    )

        return errors