"""Coverage Analyzer - relates tests to execution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.compiler_pass import CompilerPass, PassMetadata, PassResult
from core_engine.models.coverage import Coverage
from core_engine.models.knowledge_model import KnowledgeModel


class CoverageAnalyzerPass(CompilerPass):
    """Relates tests to execution structures.
    
    Answers the question: Which execution structures are exercised?
    
    Produces:
    - reachable tests
    - uncovered paths
    - integration coverage
    - endpoint coverage
    - model coverage
    
    Note: Does not make statements about sufficiency.
    """
    
    metadata = PassMetadata(
        name="coverage_analyzer",
        version="1.0.0",
        description="Relates tests to execution",
        produces=["coverage"],
        consumes=["execution_units"],
    )
    
    def execute(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> PassResult:
        """Execute the coverage analysis.
        
        Args:
            graph: The semantic graph
            model: The current knowledge model
            
        Returns:
            PassResult with coverage analysis results
        """
        diagnostics = []
        
        # Find all tests
        tests = self._find_tests(graph)
        
        # Find all nodes and edges
        all_nodes = set(graph.nodes.keys())
        all_edges = {f"edge_{i}" for i in range(len(graph.edges))}
        
        # Find covered nodes and edges (those reachable from tests)
        covered_nodes = set()
        covered_edges = set()
        
        for test_id in tests:
            # BFS from test to find what it covers
            reachable_nodes, reachable_edges = self._bfs_from_test(graph, test_id)
            covered_nodes.update(reachable_nodes)
            covered_edges.update(reachable_edges)
        
        # Find uncovered nodes and edges
        uncovered_nodes = all_nodes - covered_nodes
        uncovered_edges = all_edges - covered_edges
        
        # Calculate coverage metrics
        total_nodes = len(all_nodes)
        total_edges = len(all_edges)
        
        node_coverage = len(covered_nodes) / total_nodes if total_nodes > 0 else 0.0
        edge_coverage = len(covered_edges) / total_edges if total_edges > 0 else 0.0
        
        # Calculate endpoint coverage
        endpoints = self._find_by_type(graph, NodeType.ENDPOINT)
        covered_endpoints = [ep for ep in endpoints if ep in covered_nodes]
        endpoint_coverage = len(covered_endpoints) / len(endpoints) if endpoints else 0.0
        
        # Calculate model coverage
        models = self._find_by_type(graph, NodeType.MODEL)
        covered_models = [m for m in models if m in covered_nodes]
        model_coverage = len(covered_models) / len(models) if models else 0.0
        
        # Calculate integration coverage (cross-domain edges)
        integration_edges = self._find_integration_edges(graph)
        covered_integration = [e for e in integration_edges if e in covered_edges]
        integration_coverage = len(covered_integration) / len(integration_edges) if integration_edges else 0.0
        
        # Find uncovered paths (paths from entrypoints to sinks not covered by tests)
        uncovered_paths = self._find_uncovered_paths(graph, tests, covered_nodes)
        
        # Create coverage object
        coverage = Coverage(
            coverage_id="coverage_main",
            covered_nodes=list(covered_nodes),
            uncovered_nodes=list(uncovered_nodes),
            covered_edges=list(covered_edges),
            uncovered_edges=list(uncovered_edges),
            reachable_tests=tests,
            uncovered_paths=uncovered_paths,
            integration_coverage=integration_coverage,
            endpoint_coverage=endpoint_coverage,
            model_coverage=model_coverage,
        )
        
        # Update model with coverage
        updated_model = model.with_coverage(coverage.coverage_id)
        
        diagnostics.append(
            f"Coverage: {node_coverage:.1%} nodes, {edge_coverage:.1%} edges, "
            f"{endpoint_coverage:.1%} endpoints, {model_coverage:.1%} models, "
            f"{integration_coverage:.1%} integration"
        )
        
        return PassResult(
            pass_name=self.metadata.name,
            success=True,
            diagnostics=diagnostics,
            metadata={
                "coverage_id": coverage.coverage_id,
                "node_coverage": node_coverage,
                "edge_coverage": edge_coverage,
                "endpoint_coverage": endpoint_coverage,
                "model_coverage": model_coverage,
                "integration_coverage": integration_coverage,
                "covered_nodes_count": len(covered_nodes),
                "uncovered_nodes_count": len(uncovered_nodes),
                "covered_edges_count": len(covered_edges),
                "uncovered_edges_count": len(uncovered_edges),
            },
        ), updated_model
    
    def _find_tests(self, graph: SemanticGraph) -> List[str]:
        """Find all test nodes."""
        return self._find_by_type(graph, NodeType.TEST)
    
    def _find_by_type(self, graph: SemanticGraph, node_type: NodeType) -> List[str]:
        """Find all nodes of a specific type."""
        return [
            node_id for node_id, node in graph.nodes.items()
            if node.node_type == node_type
        ]
    
    def _bfs_from_test(
        self, graph: SemanticGraph, test_id: str
    ) -> tuple[Set[str], Set[str]]:
        """BFS from a test node to find what it covers.
        
        Returns:
            Tuple of (covered node IDs, covered edge IDs)
        """
        visited_nodes = set()
        visited_edges = set()
        queue = [test_id]
        visited_nodes.add(test_id)
        
        while queue:
            current = queue.pop(0)
            
            # Find all outgoing edges from this node
            for i, edge in enumerate(graph.edges):
                source_key = graph._node_key(edge.source)
                if source_key == current:
                    edge_id = f"edge_{i}"
                    visited_edges.add(edge_id)
                    
                    target_id = graph._node_key(edge.target)
                    
                    if target_id not in visited_nodes and target_id in graph.nodes:
                        visited_nodes.add(target_id)
                        queue.append(target_id)
        
        return visited_nodes, visited_edges
    
    def _find_integration_edges(self, graph: SemanticGraph) -> List[str]:
        """Find edges that cross domain boundaries."""
        integration_edges = []
        
        for i, edge in enumerate(graph.edges):
            source_id = graph._node_key(edge.source)
            target_id = graph._node_key(edge.target)
            
            # Get file paths
            source_node = graph.nodes.get(source_id)
            target_node = graph.nodes.get(target_id)
            
            if source_node and target_node:
                source_domain = self._get_domain(source_node.file_path)
                target_domain = self._get_domain(target_node.file_path)
                
                # If domains differ, it's an integration edge
                if source_domain != target_domain:
                    integration_edges.append(f"edge_{i}")
        
        return integration_edges
    
    def _get_domain(self, file_path: str) -> str:
        """Extract domain from file path."""
        if not file_path:
            return "unknown"
        
        # Get top-level directory
        parts = file_path.split("/")
        if parts:
            return parts[0]
        return "unknown"
    
    def _find_uncovered_paths(
        self, graph: SemanticGraph, tests: List[str], covered_nodes: Set[str]
    ) -> List[str]:
        """Find execution paths not covered by tests."""
        uncovered_paths = []
        
        # Find entrypoints
        entrypoints = self._find_by_type(graph, NodeType.ENDPOINT)
        
        # For each entrypoint, check if it's covered
        for entrypoint in entrypoints:
            if entrypoint not in covered_nodes:
                uncovered_paths.append(entrypoint)
        
        return uncovered_paths