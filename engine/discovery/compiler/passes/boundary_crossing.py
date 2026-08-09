"""Boundary Crossing Pass - identifies service boundary crossings."""
from __future__ import annotations

from engine.operational.model import OperationalChangeModel

from engine.discovery.model import Discovery, DiscoveryKind, DiscoveryFact, DiscoveryReference
from .base import DiscoveryPassContext, DiscoveryCompilerPass


class BoundaryCrossingPass(DiscoveryCompilerPass):
    """Identify execution paths that cross service boundaries.
    
    This pass answers: Which execution paths cross service boundaries?
    
    It analyzes execution chains to find transitions between services
    or modules.
    """
    
    @property
    def name(self) -> str:
        """Return the name of this pass."""
        return "boundary_crossing"
    
    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.
        
        Args:
            context: The current pass context with operational_model set.
            
        Returns:
            Updated pass context with boundary crossing discoveries appended.
        """
        if not self.validate_input(context):
            return context
        
        operational_model = context.operational_model
        if operational_model is None or operational_model.behavior is None:
            return context
        behavior_model = operational_model.behavior
        
        # Track boundary crossings across execution chains
        crossed_boundaries: list[str] = []
        service_transitions = 0
        
        # Analyze execution chains for boundary crossings
        for chain in behavior_model.execution_chains:
            previous_service = None
            
            for unit in chain.units:
                # Extract service/module from unit metadata if available
                current_service = getattr(unit, 'service', None) or getattr(unit, 'module', None)
                
                if current_service and previous_service and current_service != previous_service:
                    boundary = f"{previous_service}->{current_service}"
                    crossed_boundaries.append(boundary)
                    service_transitions += 1
                
                if current_service:
                    previous_service = current_service
        
        if not crossed_boundaries:
            return context
        
        # Create references to execution chains
        references = tuple(
            DiscoveryReference(
                artifact_type="behavior",
                artifact_id=chain.id,
                location=f"chain:{chain.behavior_id}",
            )
            for chain in behavior_model.execution_chains
            if chain.id
        )
        
        discovery = Discovery(
            id="boundary_crossing::service_transitions",
            kind=DiscoveryKind.BOUNDARY_CROSSING,
            facts=DiscoveryFact(
                crossed_boundaries=tuple(set(crossed_boundaries)),  # Deduplicate
                service_transitions=service_transitions,
            ),
            references=references,
        )
        
        context.discoveries.append(discovery)
        
        return context