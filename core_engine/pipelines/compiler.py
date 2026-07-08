"""Compiler - main entry point for the Core Engine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from language_adapters.ir.semantic_graph import SemanticGraph

from core_engine.models.compiler_pass import CompilerPass, PassResult
from core_engine.models.knowledge_model import KnowledgeModel
from core_engine.models.review_context import ReviewContext
from core_engine.pipelines.pass_manager import PassManager
from core_engine.pipelines.pipeline import Pipeline
from core_engine.pipelines.registry import PassRegistry


class Compiler:
    """Main compiler entry point.
    
    The Compiler is responsible for:
    - Managing the compilation pipeline
    - Coordinating pass execution
    - Producing final ReviewContext output
    """
    
    def __init__(self, registry: Optional[PassRegistry] = None):
        """Initialize the compiler.
        
        Args:
            registry: Optional pass registry (creates empty one if not provided)
        """
        self.pipeline = Pipeline(registry)
    
    def register_pass(self, pass_cls: Type[CompilerPass]) -> None:
        """Register a compiler pass.
        
        Args:
            pass_cls: The pass class to register
        """
        self.pipeline.register_pass(pass_cls)
    
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
        return self.pipeline.compile(
            graph, graph_id, commit_hash, stop_on_failure=stop_on_failure
        )
    
    def get_diagnostics(self) -> List[str]:
        """Get diagnostics from the last compilation.
        
        Returns:
            List of diagnostic messages
        """
        return self.pipeline.get_diagnostics()
    
    def get_timing(self) -> Dict[str, float]:
        """Get timing information from the last compilation.
        
        Returns:
            Dictionary mapping pass names to execution times
        """
        return self.pipeline.get_timing()