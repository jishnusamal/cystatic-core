"""Interaction Analyzer - discovers structural interaction groups."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.compiler_pass import CompilerPass, PassMetadata, PassResult
from core_engine.models.interaction import InteractionCluster
from core_engine.models.knowledge_model import KnowledgeModel


class InteractionAnalyzer(CompilerPass):
    """Discovers structural interaction groups.
    
    Answers the question: Which components participate together?
    
    Uses:
    - graph connectivity
    - SCC (Strongly Connected Components)
    - articulation points
    - dependency neighborhoods
    """
    
    metadata = PassMetadata(
        name="interaction_analyzer",
        version="1.0.0",
        description="Discovers structural interaction groups",
        produces=["interaction_clusters"],
        consumes=["execution_units"],
    )
    
    def execute(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> PassResult:
        """Execute the interaction analysis.
        
        Args:
            graph: The semantic graph
            model: The current knowledge model
            
        Returns:
            PassResult with interaction analysis results
        """
        diagnostics = []
        clusters = []
        
        # Find strongly connected components (SCCs)
        sccs = self._find_sccs(graph)
        for i, scc in enumerate(sccs):
            if len(scc) > 1:  # Only report SCCs with multiple nodes
                cluster = InteractionCluster(
                    cluster_id=f"cluster_scc_{i}",
                    node_ids=scc,
                    cluster_type="scc",
                    description=f"Strongly connected component with {len(scc)} nodes",
                )
                clusters.append(cluster)
        
        # Find connectivity clusters (connected components)
        connected = self._find_connected_components(graph)
        for i, component in enumerate(connected):
            if len(component) > 1:  # Only report components with multiple nodes
                cluster = InteractionCluster(
                    cluster_id=f"cluster_conn_{i}",
                    node_ids=component,
                    cluster_type="connectivity",
                    description=f"Connected component with {len(component)} nodes",
                )
                clusters.append(cluster)
        
        # Find dependency neighborhoods (nodes that share dependencies)
        neighborhoods = self._find_dependency_neighborhoods(graph)
        for i, neighborhood in enumerate(neighborhoods):
            if len(neighborhood) > 1:
                cluster = InteractionCluster(
                    cluster_id=f"cluster_neigh_{i}",
                    node_ids=neighborhood,
                    cluster_type="neighborhood",
                    description=f"Dependency neighborhood with {len(neighborhood)} nodes",
                )
                clusters.append(cluster)
        
        # Update model with clusters
        updated_model = model
        for cluster in clusters:
            updated_model = updated_model.with_execution_unit(cluster.cluster_id)
        
        diagnostics.append(
            f"Found {len(clusters)} interaction clusters "
            f"({len(sccs)} SCCs, {len(connected)} connected components, "
            f"{len(neighborhoods)} neighborhoods)"
        )
        
        return PassResult(
            pass_name=self.metadata.name,
            success=True,
            diagnostics=diagnostics,
            metadata={
                "clusters_count": len(clusters),
                "sccs_count": len(sccs),
                "connected_components_count": len(connected),
                "neighborhoods_count": len(neighborhoods),
            },
        ), updated_model
    
    def _find_sccs(self, graph: SemanticGraph) -> List[List[str]]:
        """Find strongly connected components using Tarjan's algorithm."""
        index_counter = [0]
        stack = []
        lowlink = {}
        index = {}
        on_stack = {}
        sccs = []
        
        def strongconnect(v):
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack[v] = True
            
            # Find successors
            for edge in graph.edges:
                source_key = graph._node_key(edge.source)
                if source_key == v:
                    target_key = graph._node_key(edge.target)
                    w = target_key
                    if w not in index:
                        strongconnect(w)
                        lowlink[v] = min(lowlink[v], lowlink[w])
                    elif on_stack.get(w, False):
                        lowlink[v] = min(lowlink[v], index[w])
            
            # If v is a root node, pop the stack and generate an SCC
            if lowlink[v] == index[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == v:
                        break
                sccs.append(scc)
        
        # Run Tarjan's algorithm on all nodes
        for node_id in graph.nodes:
            if node_id not in index:
                strongconnect(node_id)
        
        return sccs
    
    def _find_connected_components(self, graph: SemanticGraph) -> List[List[str]]:
        """Find connected components using BFS."""
        visited = set()
        components = []
        
        for node_id in graph.nodes:
            if node_id not in visited:
                component = []
                queue = [node_id]
                visited.add(node_id)
                
                while queue:
                    current = queue.pop(0)
                    component.append(current)
                    
                    # Find neighbors
                    for edge in graph.edges:
                        neighbor = None
                        source_key = graph._node_key(edge.source)
                        target_key = graph._node_key(edge.target)
                        if source_key == current:
                            neighbor = target_key
                        elif target_key == current:
                            neighbor = source_key
                        
                        if neighbor and neighbor in graph.nodes and neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                
                components.append(component)
        
        return components
    
    def _find_dependency_neighborhoods(self, graph: SemanticGraph) -> List[List[str]]:
        """Find nodes that share dependencies."""
        # Group nodes by their dependencies
        dep_map: Dict[str, Set[str]] = {}
        
        for edge in graph.edges:
            if edge.edge_type in (EdgeType.CALLS, EdgeType.USES, EdgeType.READS, EdgeType.WRITES):
                source_id = graph._node_key(edge.source)
                target_id = graph._node_key(edge.target)
                
                if target_id not in dep_map:
                    dep_map[target_id] = set()
                dep_map[target_id].add(source_id)
        
        # Find nodes that share dependencies
        neighborhoods = []
        for target_id, dependents in dep_map.items():
            if len(dependents) > 1:
                neighborhood = list(dependents) + [target_id]
                neighborhoods.append(neighborhood)
        
        return neighborhoods