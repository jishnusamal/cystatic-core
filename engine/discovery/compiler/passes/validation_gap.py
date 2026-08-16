"""Validation Gap Pass - identifies symbols without test coverage."""

from __future__ import annotations

from engine.discovery.model import (
    Discovery,
    DiscoveryFact,
    DiscoveryKind,
    DiscoveryReference,
)

from .base import DiscoveryCompilerPass, DiscoveryPassContext


class ValidationGapPass(DiscoveryCompilerPass):
    """Identify symbols that lack test coverage.

    This pass answers: Which symbols have no test validation?

    It reads validation data from the operational model and emits
    discoveries for untested symbols.
    """

    @property
    def name(self) -> str:
        """Return the name of this pass."""
        return "validation_gap"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.

        Args:
            context: The current pass context with operational_model set.

        Returns:
            Updated pass context with validation gap discoveries appended.
        """
        if not self.validate_input(context):
            return context

        operational_model = context.operational_model
        if operational_model is None:
            return context

        # Check if validation model is present
        if (
            not hasattr(operational_model, "validation")
            or operational_model.validation is None
        ):
            return context

        validation_model = operational_model.validation

        # Extract untested symbols if available
        untested_symbol_ids: tuple[str, ...] = ()
        if hasattr(validation_model, "untested_symbols"):
            untested_symbol_ids = tuple(validation_model.untested_symbols)
        elif hasattr(validation_model, "untested_symbol_ids"):
            untested_symbol_ids = tuple(validation_model.untested_symbol_ids)

        if not untested_symbol_ids:
            return context

        # Calculate coverage ratio if available
        coverage_ratio = 0.0
        if hasattr(validation_model, "coverage_ratio"):
            coverage_ratio = float(validation_model.coverage_ratio)
        elif hasattr(validation_model, "test_coverage_ratio"):
            coverage_ratio = float(validation_model.test_coverage_ratio)

        # Create references to validation artifacts
        references = tuple(
            DiscoveryReference(
                artifact_type="validation",
                artifact_id=f"validation_gap::{symbol_id}",
                location=symbol_id,
            )
            for symbol_id in untested_symbol_ids
        )

        discovery = Discovery(
            id="validation_gap::untested_symbols",
            kind=DiscoveryKind.VALIDATION_GAP,
            facts=DiscoveryFact(
                untested_symbol_ids=untested_symbol_ids,
                validation_coverage_ratio=coverage_ratio,
            ),
            references=references,
        )

        context.discoveries.append(discovery)

        return context
