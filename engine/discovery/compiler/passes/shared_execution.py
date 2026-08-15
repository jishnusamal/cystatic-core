"""Shared Execution Pass - identifies symbols shared across behaviors."""

from __future__ import annotations

from engine.operational.model import OperationalChangeModel

from engine.discovery.model import (
    Discovery,
    DiscoveryKind,
    DiscoveryFact,
    DiscoveryReference,
)
from .base import DiscoveryPassContext, DiscoveryCompilerPass


class SharedExecutionPass(DiscoveryCompilerPass):
    """Identify symbols that are shared across multiple behaviors.

    This pass answers: Which symbols participate in shared execution?

    It reads shared_executions from the behavior model and emits
    discoveries for each group of shared symbols.
    """

    @property
    def name(self) -> str:
        """Return the name of this pass."""
        return "shared_execution"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.

        Args:
            context: The current pass context with operational_model set.

        Returns:
            Updated pass context with shared execution discoveries appended.
        """
        if not self.validate_input(context):
            return context

        operational_model = context.operational_model
        if operational_model is None or operational_model.behavior is None:
            return context
        behavior_model = operational_model.behavior

        # Get all shared executions
        shared_executions = behavior_model.shared_executions

        if not shared_executions:
            return context

        # Group shared executions by symbol_id
        shared_by_symbol: dict[str, list] = {}
        for shared_exec in shared_executions:
            symbol_id = shared_exec.symbol_id
            if symbol_id not in shared_by_symbol:
                shared_by_symbol[symbol_id] = []
            shared_by_symbol[symbol_id].append(shared_exec)

        # Emit a discovery for each shared symbol
        for symbol_id, shared_list in shared_by_symbol.items():
            # Collect all behavior IDs from used_by tuples
            behavior_ids: set[str] = set()
            for se in shared_list:
                behavior_ids.update(se.used_by)
            behavior_ids_tuple = tuple(behavior_ids)

            # Create references to the shared executions
            references = tuple(
                DiscoveryReference(
                    artifact_type="behavior",
                    artifact_id=se.id,
                    location=symbol_id,
                )
                for se in shared_list
            )

            discovery = Discovery(
                id=f"shared_execution::{symbol_id}",
                kind=DiscoveryKind.SHARED_EXECUTION,
                facts=DiscoveryFact(
                    shared_symbol_ids=(symbol_id,),
                    behavior_count=len(behavior_ids_tuple),
                ),
                references=references,
            )

            context.discoveries.append(discovery)

        return context
