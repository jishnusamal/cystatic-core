"""Execution Analyzer - discovers executable structures."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.compiler_pass import CompilerPass, PassMetadata, PassResult
from core_engine.models.execution import ExecutionUnit
from core_engine.models.knowledge_model import KnowledgeModel


class ExecutionAnalyzer(CompilerPass):
    """Discovers executable structures in the graph.
    
    Answers the question: What executable structures can be proven?
    
    Produces:
    - entrypoints
    - functions
    - reads
    - writes
    - queries
    - events
    - transactions
    - tests
    - external calls
    """
    
    metadata = PassMetadata(
        name="execution_analyzer",
        version="1.0.0",
        description="Discovers executable structures",
        produces=["execution_units"],
        consumes=[],
    )
    
    def execute(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> PassResult:
        """Execute the execution analysis.
        
        Args:
            graph: The semantic graph
            model: The current knowledge model
            
        Returns:
            PassResult with execution analysis results
        """
        diagnostics = []
        
        # Find entrypoints (endpoints, tests with no incoming calls)
        entrypoints = self._find_entrypoints(graph)
        
        # Find all executable units by type
        functions = self._find_by_type(graph, NodeType.FUNCTION)
        methods = self._find_by_type(graph, NodeType.METHOD)
        queries = self._find_by_type(graph, NodeType.QUERY)
        transactions = self._find_by_type(graph, NodeType.TRANSACTION)
        tests = self._find_by_type(graph, NodeType.TEST)
        external_calls = self._find_external_calls(graph)
        
        # Find reads and writes
        reads = self._find_operations(graph, EdgeType.READS)
        writes = self._find_operations(graph, EdgeType.WRITES)
        
        # Find events
        events = self._find_by_type(graph, NodeType.EVENT)
        
        # Create execution units
        execution_units = []
        
        # Entrypoint units
        for node_id in entrypoints:
            unit = ExecutionUnit(
                unit_id=f"exec_{node_id}",
                unit_type="entrypoint",
                name=node_id.split(":")[1] if ":" in node_id else node_id,
                file_path=self._get_file_path(graph, node_id),
                node_ids=[node_id],
                change_type=self._get_change_type(graph, node_id),
            )
            execution_units.append(unit)
        
        # Function units
        for node_id in functions:
            unit = ExecutionUnit(
                unit_id=f"exec_{node_id}",
                unit_type="function",
                name=node_id.split(":")[1] if ":" in node_id else node_id,
                file_path=self._get_file_path(graph, node_id),
                node_ids=[node_id],
                change_type=self._get_change_type(graph, node_id),
            )
            execution_units.append(unit)
        
        # Query units
        for node_id in queries:
            unit = ExecutionUnit(
                unit_id=f"exec_{node_id}",
                unit_type="query",
                name=node_id.split(":")[1] if ":" in node_id else node_id,
                file_path=self._get_file_path(graph, node_id),
                node_ids=[node_id],
                change_type=self._get_change_type(graph, node_id),
            )
            execution_units.append(unit)
        
        # Transaction units
        for node_id in transactions:
            unit = ExecutionUnit(
                unit_id=f"exec_{node_id}",
                unit_type="transaction",
                name=node_id.split(":")[1] if ":" in node_id else node_id,
                file_path=self._get_file_path(graph, node_id),
                node_ids=[node_id],
                change_type=self._get_change_type(graph, node_id),
            )
            execution_units.append(unit)
        
        # Test units
        for node_id in tests:
            unit = ExecutionUnit(
                unit_id=f"exec_{node_id}",
                unit_type="test",
                name=node_id.split(":")[1] if ":" in node_id else node_id,
                file_path=self._get_file_path(graph, node_id),
                node_ids=[node_id],
                change_type=self._get_change_type(graph, node_id),
            )
            execution_units.append(unit)
        
        # Update model with execution units
        updated_model = model
        for unit in execution_units:
            updated_model = updated_model.with_execution_unit(unit.unit_id)
        
        diagnostics.append(
            f"Found {len(execution_units)} execution units "
            f"({len(entrypoints)} entrypoints, {len(functions)} functions, "
            f"{len(queries)} queries, {len(transactions)} transactions, "
            f"{len(tests)} tests)"
        )
        
        return PassResult(
            pass_name=self.metadata.name,
            success=True,
            diagnostics=diagnostics,
            metadata={
                "execution_units_count": len(execution_units),
                "entrypoints_count": len(entrypoints),
                "functions_count": len(functions),
                "queries_count": len(queries),
                "transactions_count": len(transactions),
                "tests_count": len(tests),
                "reads_count": len(reads),
                "writes_count": len(writes),
                "events_count": len(events),
                "external_calls_count": len(external_calls),
            },
        ), updated_model
    
    def _find_entrypoints(self, graph: SemanticGraph) -> List[str]:
        """Find entrypoint nodes (endpoints, tests)."""
        entrypoints = []
        
        # Endpoints are entrypoints
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.ENDPOINT:
                entrypoints.append(node_id)
        
        # Tests are entrypoints
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.TEST:
                entrypoints.append(node_id)
        
        return entrypoints
    
    def _find_by_type(self, graph: SemanticGraph, node_type: NodeType) -> List[str]:
        """Find all nodes of a specific type."""
        return [
            node_id for node_id, node in graph.nodes.items()
            if node.node_type == node_type
        ]
    
    def _find_operations(self, graph: SemanticGraph, edge_type: EdgeType) -> List[str]:
        """Find all edges of a specific operation type."""
        return [
            f"edge_{i}" for i, edge in enumerate(graph.edges)
            if edge.edge_type == edge_type
        ]
    
    def _find_external_calls(self, graph: SemanticGraph) -> List[str]:
        """Find external service calls."""
        external = []
        
        # Look for EXTERNAL_SERVICE nodes
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.EXTERNAL_SERVICE:
                external.append(node_id)
        
        # Look for edges to external services
        for edge in graph.edges:
            if edge.edge_type == EdgeType.SENDS_HTTP:
                target_key = graph._node_key(edge.target)
                if target_key not in external:
                    external.append(target_key)
        
        return external
    
    def _get_file_path(self, graph: SemanticGraph, node_id: str) -> str:
        """Get file path for a node."""
        node = graph.nodes.get(node_id)
        return node.file_path if node else ""
    
    def _get_change_type(self, graph: SemanticGraph, node_id: str) -> str:
        """Get change type for a node."""
        node = graph.nodes.get(node_id)
        return node.change_type if node else "unknown"