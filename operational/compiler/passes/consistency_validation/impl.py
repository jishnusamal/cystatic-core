"""Pass 2 — Consistency Validation.

Question: Are all referenced entities internally consistent?

Checks:
- Every changed symbol exists in RepositoryModel.
- Every behavior references valid symbols.
- Every entry point belongs to RepositoryModel.
- Every execution graph references known nodes.

This is compiler validation, not business validation.
"""

from operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)


class ConsistencyValidationPass(OperationalCompilerPass):
    """
    Pass 2 of Operational compilation.

    Validates that all references across the composed models are internally
    consistent. This catches data integrity issues before downstream consumers
    (renderers, AI) process the model.
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
        errors: list[str] = []

        # Build a set of all known symbol IDs from the repository model
        known_symbol_ids = {s.id for s in model.repository.symbols}

        # 1. Every changed symbol exists in RepositoryModel
        errors.extend(
            self._validate_changed_symbols(model, known_symbol_ids)
        )

        # 2. Every behavior references valid symbols
        errors.extend(
            self._validate_behavior_symbols(model, known_symbol_ids)
        )

        # 3. Every entry point belongs to RepositoryModel
        errors.extend(
            self._validate_entry_points(model, known_symbol_ids)
        )

        # 4. Every execution graph references known nodes
        errors.extend(
            self._validate_execution_graphs(model, known_symbol_ids)
        )

        context.consistency_errors = errors
        return context

    def _validate_changed_symbols(
        self,
        model: "OperationalChangeModel",
        known_symbol_ids: set[str],
    ) -> list[str]:
        """Check that every changed symbol exists in the repository model."""
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