"""State Mutation Pass - identifies state mutations."""
from __future__ import annotations

from operational.model import OperationalChangeModel

from ..model import Discovery, DiscoveryKind, DiscoveryFact, DiscoveryReference
from .base import DiscoveryPassContext, DiscoveryCompilerPass


class StateMutationPass(DiscoveryCompilerPass):
    """Identify state mutations.
    
    This pass answers: Which state is being mutated?
    
    It analyzes the data model to find state mutations and their sources.
    """
    
    @property
    def name(self) -> str:
        """Return the name of this pass."""
        return "state_mutation"
    
    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.
        
        Args:
            context: The current pass context with operational_model set.
            
        Returns:
            Updated pass context with state mutation discoveries appended.
        """
        if not self.validate_input(context):
            return context
        
        operational_model = context.operational_model
        
        # Check if data model is present
        if not hasattr(operational_model, 'data') or operational_model.data is None:
            return context
        
        data_model = operational_model.data
        
        # Extract mutated state if available
        mutated_state: tuple[str, ...] = ()
        if hasattr(data_model, 'mutated_state'):
            mutated_state = tuple(data_model.mutated_state)
        elif hasattr(data_model, 'mutated_entities'):
            mutated_state = tuple(data_model.mutated_entities)
        elif hasattr(data_model, 'tables'):
            # If tables are present, use them as mutated state
            mutated_state = tuple(data_model.tables)
        
        if not mutated_state:
            return context
        
        # Extract mutation sources if available
        mutation_sources: tuple[str, ...] = ()
        if hasattr(data_model, 'mutation_sources'):
            mutation_sources = tuple(data_model.mutation_sources)
        elif hasattr(data_model, 'write_operations'):
            mutation_sources = tuple(data_model.write_operations)
        
        # Create references to data artifacts
        references = tuple(
            DiscoveryReference(
                artifact_type="data",
                artifact_id=state_id,
                location=state_id,
            )
            for state_id in mutated_state
        )
        
        discovery = Discovery(
            id="state_mutation::mutated_state",
            kind=DiscoveryKind.STATE_MUTATION,
            facts=DiscoveryFact(
                mutated_state=mutated_state,
                mutation_sources=mutation_sources,
            ),
            references=references,
        )
        
        context.discoveries.append(discovery)
        
        return context