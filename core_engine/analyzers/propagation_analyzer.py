"""Propagation Analyzer - computes downstream reachability."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.compiler_pass import CompilerPass, PassMetadata, PassResult
from core_engine.models.knowledge_model import KnowledgeModel
from core_engine.models.propagation import PropagationPath


class PropagationAnalyzer(CompilerPass):
    """Computes downstream reachability from changed nodes.
    
    Answers the question: Which nodes are deterministically reachable 
    from changed nodes?
    
    Includes:
    - shortest paths
    - all reachable endpoints
    - reachable models
    - reachable events
    - reachable workers
    - reachable APIs
    """
    
    metadata = PassMetadata(
        name="propagation_analyzer",
        version="1.0.0",
        description="Computes downstream reachability",
        produces=["propagation_paths"],
        consumes=["execution_units", "interaction_clusters"],
    )
    
    def execute(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> PassResult:
        """Execute the propagation analysis.
        
        Args:
            graph: The semantic graph
            model: The current knowledge model
            
        Returns:
            PassResult with propagation analysis results
        """
        diagnostics = []
        propagation_paths = []
        
        # Find changed nodes
        changed_nodes = self._find_changed_nodes(graph)
        
        # For each changed node, compute reachable nodes
        for source_id in changed_nodes:
            # BFS to find all reachable nodes
            reachable_nodes, reachable_edges = self._bfs(graph, source_id)
            
            if reachable_nodes:
                # Categorize reachable nodes
                reachable_models = [
                    n for n in reachable_nodes
                    if graph.nodes.get(n, NodeType.MODEL)
                ]
                reachable_events = [
                    n for n in reachable_nodes
                    if graph.nodes.get(n, NodeType.EVENT)
                ]
                reachable_apis = [
                    n for n in reachable_nodes
                    if graph.nodes.get(n, NodeType.ENDPOINT)
                ]
                
                # Create propagation path
                path = PropagationPath(
                    path_id=f"prop_{source_id}",
                    source_node_id=source_id,
                    reachable_node_ids=reachable_nodes,
                    reachable_edge_ids=reachable_edges,
                    path_type="all",
                )
                propagation_paths.append(path)
        
        # Update model with propagation paths
        updated_model = model
        for path in propagation_paths:
            updated_model = updated_model.with_execution_unit(path.path_id)
        
        diagnostics.append(
            f"Found {len(propagation_paths)} propagation paths "
            f"from {len(changed_nodes)} changed nodes"
        )
        
        return PassResult(
            pass_name=self.metadata.name,
            success=True,
            diagnostics=diagnostics,
            metadata={
                "propagation_paths_count": len(propagation_paths),
                "changed_nodes_count": len(changed_nodes),
            },
        ), updated_model
    
    def _find_changed_nodes(self, graph: SemanticGraph) -> List[str]:
        """Find all changed nodes in the graph."""
        changed = []
        for node_id, node in graph.nodes.items():
            if node.change_type in ("added", "modified", "removed"):
                changed.append(node_id)
        return changed
    
    def _bfs(
        self, graph: SemanticGraph, start_id: str
    ) -> tuple[List[str], List[str]]:
        """Breadth-first search from a start node.
        
        Returns:
            Tuple of (reachable node IDs, reachable edge IDs)
        """
        visited_nodes = set()
        visited_edges = set()
        queue = [start_id]
        visited_nodes.add(start_id)
        
        while queue:
            current = queue.pop(0)
            
            # Find all outgoing edges
            for i, edge in enumerate(graph.edges):
                source_key = graph._node_key(edge.source)
                if source_key == current:
                    edge_id = f"edge_{i}"
                    if edge_id not in visited_edges:
                        visited_edges.add(edge_id)
                    
                    target_id = graph._node_key(edge.target)
                    
                    if target_id not in visited_nodes and target_id in graph.nodes:
                        visited_nodes.add(target_id)
                        queue.append(target_id)
        
        return list(visited_nodes), list(visited_edges)