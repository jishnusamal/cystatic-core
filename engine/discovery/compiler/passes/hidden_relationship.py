"""Hidden Relationship Pass - identifies non-obvious relationships between symbols."""

from __future__ import annotations

from engine.operational.model import OperationalChangeModel

from engine.discovery.model import (
    Discovery,
    DiscoveryKind,
    DiscoveryFact,
    DiscoveryReference,
)
from .base import DiscoveryPassContext, DiscoveryCompilerPass


class HiddenRelationshipPass(DiscoveryCompilerPass):
    """Identify non-obvious relationships between symbols.

    This pass answers: Which symbols have hidden relationships?

    It analyzes the behavior model to find symbols that are related
    but not directly connected in execution chains.
    """

    @property
    def name(self) -> str:
        """Return the name of this pass."""
        return "hidden_relationship"

    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.

        Args:
            context: The current pass context with operational_model set.

        Returns:
            Updated pass context with hidden relationship discoveries appended.
        """
        if not self.validate_input(context):
            return context

        operational_model = context.operational_model
        if operational_model is None or operational_model.behavior is None:
            return context
        behavior_model = operational_model.behavior

        # Find symbols that appear in multiple behaviors but not in shared_executions
        # This indicates a hidden relationship
        behavior_symbol_map: dict[str, set[str]] = {}

        for behavior in behavior_model.behaviors:
            behavior_id = behavior.id
            # Collect symbols from execution chains
            symbol_ids: set[str] = set()
            for chain in behavior_model.execution_chains:
                if chain.behavior_id == behavior_id:
                    for unit in chain.units:
                        if hasattr(unit, "symbol_id"):
                            symbol_ids.add(unit.symbol_id)

            behavior_symbol_map[behavior_id] = symbol_ids

        # Find symbols that appear in multiple behaviors
        symbol_to_behaviors: dict[str, list[str]] = {}
        for behavior_id, symbols in behavior_symbol_map.items():
            for symbol_id in symbols:
                if symbol_id not in symbol_to_behaviors:
                    symbol_to_behaviors[symbol_id] = []
                symbol_to_behaviors[symbol_id].append(behavior_id)

        # Filter to only symbols in multiple behaviors
        hidden_relationships = {
            symbol_id: behavior_ids
            for symbol_id, behavior_ids in symbol_to_behaviors.items()
            if len(behavior_ids) > 1
        }

        if not hidden_relationships:
            return context

        # Create discoveries for each hidden relationship
        for symbol_id, behavior_ids in hidden_relationships.items():
            # Create pairs of related behaviors
            related_pairs = tuple(
                (behavior_ids[i], behavior_ids[j])
                for i in range(len(behavior_ids))
                for j in range(i + 1, len(behavior_ids))
            )

            references = tuple(
                DiscoveryReference(
                    artifact_type="behavior",
                    artifact_id=behavior_id,
                    location=symbol_id,
                )
                for behavior_id in behavior_ids
            )

            discovery = Discovery(
                id=f"hidden_relationship::{symbol_id}",
                kind=DiscoveryKind.HIDDEN_RELATIONSHIP,
                facts=DiscoveryFact(
                    related_symbol_pairs=related_pairs,
                    relationship_type="multi_behavior_presence",
                ),
                references=references,
            )

            context.discoveries.append(discovery)

        return context
