"""Pipeline - high-level compiler pipeline interface."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from language_adapters.ir.semantic_graph import SemanticGraph

from core_engine.models.compiler_pass import CompilerPass, PassResult
from core_engine.models.knowledge_model import KnowledgeModel
from core_engine.models.review_context import ReviewContext
from core_engine.pipelines.pass_manager import PassManager
from core_engine.pipelines.registry import PassRegistry


class Pipeline:
    """High-level compiler pipeline.
    
    Orchestrates the execution of compiler passes to transform
    a SemanticGraph into a KnowledgeModel and ReviewContext.
    """
    
    def __init__(self, registry: Optional[PassRegistry] = None):
        """Initialize the pipeline.
        
        Args:
            registry: Optional pass registry (creates empty one if not provided)
        """
        self.registry = registry or PassRegistry()
        self.pass_manager = PassManager(self.registry)
    
    def register_pass(self, pass_cls: Type[CompilerPass]) -> None:
        """Register a compiler pass.
        
        Args:
            pass_cls: The pass class to register
        """
        self.registry.register(pass_cls)
    
    def compile(
        self,
        graph: SemanticGraph,
        graph_id: str,
        commit_hash: str,
        stop_on_failure: bool = False,
    ) -> tuple[KnowledgeModel, List[PassResult]]:
        """Compile a semantic graph into a knowledge model.
        
        Args:
            graph: The semantic graph to compile
            graph_id: Unique identifier for the graph
            commit_hash: The commit hash this graph represents
            stop_on_failure: If True, stop on first pass failure
            
        Returns:
            Tuple of (knowledge model, pass results)
        """
        # Create initial empty model
        model = KnowledgeModel.empty(graph_id, commit_hash)
        
        # Execute all passes
        model, results = self.pass_manager.execute_all(
            graph, model, stop_on_failure=stop_on_failure
        )
        
        return model, results
    
    def get_diagnostics(self) -> List[str]:
        """Get diagnostics from the last compilation.
        
        Returns:
            List of diagnostic messages
        """
        return self.pass_manager.get_diagnostics()
    
    def get_timing(self) -> Dict[str, float]:
        """Get timing information from the last compilation.
        
        Returns:
            Dictionary mapping pass names to execution times
        """
        return self.pass_manager.get_timing()