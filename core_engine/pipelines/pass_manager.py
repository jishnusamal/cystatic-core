"""Pass manager - executes compiler passes with diagnostics."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Type

from language_adapters.ir.semantic_graph import SemanticGraph

from core_engine.models.compiler_pass import CompilerPass, PassResult
from core_engine.models.knowledge_model import KnowledgeModel
from core_engine.pipelines.registry import PassRegistry


class PassManager:
    """Manages execution of compiler passes.
    
    Responsibilities:
    - Execute passes in dependency order
    - Collect diagnostics
    - Track pass metadata
    - Handle pass failures
    """
    
    def __init__(self, registry: PassRegistry):
        """Initialize with a pass registry.
        
        Args:
            registry: The pass registry containing all passes
        """
        self.registry = registry
        self._results: Dict[str, PassResult] = {}
        self._timing: Dict[str, float] = {}
    
    def execute_pass(
        self,
        pass_cls: Type[CompilerPass],
        graph: SemanticGraph,
        model: KnowledgeModel,
    ) -> tuple[KnowledgeModel, PassResult]:
        """Execute a single pass.
        
        Args:
            pass_cls: The pass class to execute
            graph: The semantic graph (read-only)
            model: The current knowledge model
            
        Returns:
            Tuple of (enriched model, pass result)
        """
        pass_instance = pass_cls()
        start_time = time.time()
        
        try:
            result = pass_instance.execute(graph, model)
            elapsed = time.time() - start_time
            self._results[pass_instance.metadata.name] = result
            self._timing[pass_instance.metadata.name] = elapsed
            
            # Passes return (PassResult, updated_model) or just PassResult
            if isinstance(result, tuple):
                pass_result, updated_model = result
                return updated_model, pass_result
            else:
                return model, result
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = f"Pass '{pass_instance.metadata.name}' failed: {str(e)}"
            result = PassResult(
                pass_name=pass_instance.metadata.name,
                success=False,
                diagnostics=[error_msg],
            )
            self._results[pass_instance.metadata.name] = result
            self._timing[pass_instance.metadata.name] = elapsed
            
            return model, result
    
    def execute_all(
        self,
        graph: SemanticGraph,
        initial_model: KnowledgeModel,
        stop_on_failure: bool = False,
    ) -> tuple[KnowledgeModel, List[PassResult]]:
        """Execute all registered passes in dependency order.
        
        Args:
            graph: The semantic graph (read-only)
            initial_model: The initial knowledge model
            stop_on_failure: If True, stop execution on first failure
            
        Returns:
            Tuple of (final model, list of pass results)
        """
        model = initial_model
        results = []
        
        # Get passes in topological order
        sorted_passes = self.registry.topological_sort()
        
        for pass_cls in sorted_passes:
            model, result = self.execute_pass(pass_cls, graph, model)
            results.append(result)
            
            if not result.success and stop_on_failure:
                break
        
        return model, results
    
    def get_results(self) -> Dict[str, PassResult]:
        """Get all pass results from the last execution.
        
        Returns:
            Dictionary mapping pass names to results
        """
        return self._results.copy()
    
    def get_timing(self) -> Dict[str, float]:
        """Get execution timing for all passes.
        
        Returns:
            Dictionary mapping pass names to execution times (seconds)
        """
        return self._timing.copy()
    
    def get_diagnostics(self) -> List[str]:
        """Get all diagnostics from the last execution.
        
        Returns:
            List of all diagnostic messages
        """
        diagnostics = []
        for result in self._results.values():
            diagnostics.extend(result.diagnostics)
        return diagnostics
    
    def clear(self) -> None:
        """Clear all results and timing data."""
        self._results.clear()
        self._timing.clear()