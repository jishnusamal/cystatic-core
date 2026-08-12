"""Shared Dependency Pass - identifies dependencies shared across behaviors."""
from __future__ import annotations

from engine.operational.model import OperationalChangeModel

from engine.discovery.model import Discovery, DiscoveryKind, DiscoveryFact, DiscoveryReference
from .base import DiscoveryPassContext, DiscoveryCompilerPass


class SharedDependencyPass(DiscoveryCompilerPass):
    """Identify dependencies shared across multiple behaviors.
    
    This pass answers: Which dependencies are shared across behaviors?
    
    It analyzes the dependency model to find dependencies that are
    used by multiple behaviors.
    """
    
    @property
    def name(self) -> str:
        """Return the name of this pass."""
        return "shared_dependency"
    
    def run(self, context: DiscoveryPassContext) -> DiscoveryPassContext:
        """Execute the pass and return updated context.
        
        Args:
            context: The current pass context with operational_model set.
            
        Returns:
            Updated pass context with shared dependency discoveries appended.
        """
        if not self.validate_input(context):
            return context
        
        operational_model = context.operational_model
        if operational_model is None:
            return context
        
        # Check if dependency model is present
        if not hasattr(operational_model, 'dependency') or operational_model.dependency is None:
            return context
        
        dependency_model = operational_model.dependency
        
        # Extract shared dependencies if available
        shared_dependencies: tuple[str, ...] = ()
        if hasattr(dependency_model, 'shared_dependencies'):
            shared_dependencies = tuple(dependency_model.shared_dependencies)
        elif hasattr(dependency_model, 'common_dependencies'):
            shared_dependencies = tuple(dependency_model.common_dependencies)
        
        if not shared_dependencies:
            return context
        
        # Count dependencies
        dependency_count = len(shared_dependencies)
        
        # Create references to dependency artifacts
        references = tuple(
            DiscoveryReference(
                artifact_type="dependency",
                artifact_id=dep_id,
                location=dep_id,
            )
            for dep_id in shared_dependencies
        )
        
        discovery = Discovery(
            id="shared_dependency::common_dependencies",
            kind=DiscoveryKind.SHARED_DEPENDENCY,
            facts=DiscoveryFact(
                shared_dependencies=shared_dependencies,
                dependency_count=dependency_count,
            ),
            references=references,
        )
        
        context.discoveries.append(discovery)
        
        return context