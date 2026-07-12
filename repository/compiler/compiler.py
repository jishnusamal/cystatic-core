"""Repository compiler - orchestrates compilation passes."""

from typing import Any

from .passes import (
    PassContext,
    SymbolCollectionPass,
    ReferenceResolutionPass,
    CallGraphPass,
    EndpointDiscoveryPass,
)
from repository.model import RepositoryModel


class RepositoryCompiler:
    """
    Compiles a semantic graph into a Repository Model.
    
    This is the main entry point for Phase 1 compilation.
    It orchestrates the execution of all compiler passes in order.
    """
    
    def __init__(self):
        """Initialize the compiler with all passes."""
        self.passes = [
            SymbolCollectionPass(),
            ReferenceResolutionPass(),
            CallGraphPass(),
            EndpointDiscoveryPass(),
        ]
    
    def compile(self, semantic_graph: dict[str, Any]) -> RepositoryModel:
        """
        Compile a semantic graph into a Repository Model.
        
        Args:
            semantic_graph: Language-independent semantic facts from language adapter
            
        Returns:
            RepositoryModel containing the complete repository representation
        """
        # Initialize pass context with semantic graph
        context = PassContext(metadata={'semantic_graph': semantic_graph})
        
        # Execute each pass in sequence
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)
        
        # Create and return the repository model
        return RepositoryModel(
            symbols=frozenset(context.symbols),
            call_graph=context.call_graph,
            reference_graph=context.reference_graph,
            entry_points=tuple(context.entry_points)
        )
    
    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]