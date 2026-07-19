"""Deep Execution Pass - identifies deep execution paths."""
from __future__ import annotations

from operational.model import OperationalChangeModel

from ..model import Discovery, DiscoveryKind, DiscoveryFact, DiscoveryReference
from .base import DiscoveryPassContext, DiscoveryCompilerPass


class DeepExecutionPass(DiscoveryCompilerPass):
    """Identify deep execution paths.
    
    This pass answers: Which execution paths are deepest?
    
    It analyzes execution chains to find the maximum execution depth
    and identify deep paths.
    """
    
    @property
    def name(self) -> str:
        """Return the name of this pass."""
        return "deep_execution"
    
    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.
        
        Args:
            context: The current pass context with operational_model set.
            
        Returns:
            Updated pass context with deep execution discoveries appended.
        """
        if not self.validate_input(context):
            return context
        
        operational_model = context.operational_model
        behavior_model = operational_model.behavior
        
        # Find maximum execution depth
        max_depth = behavior_model.execution_depth
        
        if max_depth == 0:
            return context
        
        # Find deep paths (paths with depth >= max_depth * 0.7)
        deep_threshold = max(1, int(max_depth * 0.7))
        deep_paths: list[str] = []
        
        for chain in behavior_model.execution_chains:
            chain_depth = len(chain.units)
            if chain_depth >= deep_threshold:
                deep_paths.append(chain.id)
        
        if not deep_paths:
            return context
        
        # Create references to execution chains
        references = tuple(
            DiscoveryReference(
                artifact_type="behavior",
                artifact_id=chain_id,
                location=f"depth:{max_depth}",
            )
            for chain_id in deep_paths
        )
        
        discovery = Discovery(
            id="deep_execution::max_depth",
            kind=DiscoveryKind.DEEP_EXECUTION,
            facts=DiscoveryFact(
                max_depth=max_depth,
                deep_paths=tuple(deep_paths),
            ),
            references=references,
        )
        
        context.discoveries.append(discovery)
        
        return context