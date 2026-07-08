"""Signal Detector - generates deterministic observations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.compiler_pass import CompilerPass, PassMetadata, PassResult
from core_engine.models.knowledge_model import KnowledgeModel
from core_engine.models.signal import Signal, SignalCategory


class SignalDetector(CompilerPass):
    """Generates deterministic observations from the graph.
    
    Produces signals like:
    - WRITE_PATH_CHANGED
    - PUBLIC_API_CHANGED
    - SCHEMA_CHANGED
    - EVENT_FLOW_CHANGED
    - TRANSACTION_BOUNDARY_CHANGED
    - NO_REACHABLE_TEST
    - EXTERNAL_SERVICE_CHANGED
    - CACHE_PATH_CHANGED
    
    Does NOT produce:
    - HIGH_RISK
    - BREAKS_CHECKOUT
    - LIKELY_BUG
    
    Those belong to the LLM.
    """
    
    metadata = PassMetadata(
        name="signal_detector",
        version="1.0.0",
        description="Generates deterministic observations",
        produces=["signals"],
        consumes=[
            "execution_units",
            "propagation_paths",
            "coverage",
            "api_changes",
            "event_changes",
            "schema_changes",
            "migration_changes",
            "external_service_calls",
            "queue_changes",
            "cache_changes",
        ],
    )
    
    def execute(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> PassResult:
        """Execute the signal detection.
        
        Args:
            graph: The semantic graph
            model: The current knowledge model
            
        Returns:
            PassResult with signal detection results
        """
        diagnostics = []
        signals = []
        
        # Detect write path changes
        write_signals = self._detect_write_path_changes(graph, model)
        signals.extend(write_signals)
        
        # Detect public API changes
        api_signals = self._detect_api_changes(graph, model)
        signals.extend(api_signals)
        
        # Detect schema changes
        schema_signals = self._detect_schema_changes(graph, model)
        signals.extend(schema_signals)
        
        # Detect event flow changes
        event_signals = self._detect_event_changes(graph, model)
        signals.extend(event_signals)
        
        # Detect transaction boundary changes
        transaction_signals = self._detect_transaction_changes(graph, model)
        signals.extend(transaction_signals)
        
        # Detect no reachable test
        test_signals = self._detect_no_test_coverage(graph, model)
        signals.extend(test_signals)
        
        # Detect external service changes
        external_signals = self._detect_external_service_changes(graph, model)
        signals.extend(external_signals)
        
        # Detect cache path changes
        cache_signals = self._detect_cache_changes(graph, model)
        signals.extend(cache_signals)
        
        # Update model with signals
        updated_model = model
        for signal in signals:
            updated_model = updated_model.with_signal(signal.signal_id)
        
        diagnostics.append(
            f"Detected {len(signals)} signals"
        )
        
        return PassResult(
            pass_name=self.metadata.name,
            success=True,
            diagnostics=diagnostics,
            metadata={
                "signals_count": len(signals),
                "signal_names": [s.name for s in signals],
            },
        ), updated_model
    
    def _detect_write_path_changes(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> List[Signal]:
        """Detect write path changes."""
        signals = []
        
        # Find write edges
        write_edges = [e for e in graph.edges if e.edge_type == EdgeType.WRITES]
        
        if write_edges:
            node_ids = []
            for edge in write_edges:
                source_id = graph._node_key(edge.source)
                target_id = graph._node_key(edge.target)
                node_ids.extend([source_id, target_id])
            
            signal = Signal(
                signal_id="signal_write_path_changed",
                name="WRITE_PATH_CHANGED",
                category=SignalCategory.PERSISTENCE,
                description="Write path has changed in the system",
                rule_name="signal_detector",
                node_ids=list(set(node_ids)),
                edge_ids=[f"edge_{i}" for i in range(len(write_edges))],
            )
            signals.append(signal)
        
        return signals
    
    def _detect_api_changes(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> List[Signal]:
        """Detect public API changes."""
        signals = []
        
        if model.api_changes:
            signal = Signal(
                signal_id="signal_public_api_changed",
                name="PUBLIC_API_CHANGED",
                category=SignalCategory.API,
                description="Public API has changed",
                rule_name="signal_detector",
                node_ids=model.api_changes,
            )
            signals.append(signal)
        
        return signals
    
    def _detect_schema_changes(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> List[Signal]:
        """Detect schema changes."""
        signals = []
        
        if model.schema_changes:
            signal = Signal(
                signal_id="signal_schema_changed",
                name="SCHEMA_CHANGED",
                category=SignalCategory.SCHEMA,
                description="Schema has changed",
                rule_name="signal_detector",
                node_ids=model.schema_changes,
            )
            signals.append(signal)
        
        return signals
    
    def _detect_event_changes(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> List[Signal]:
        """Detect event flow changes."""
        signals = []
        
        if model.event_changes:
            signal = Signal(
                signal_id="signal_event_flow_changed",
                name="EVENT_FLOW_CHANGED",
                category=SignalCategory.EVENT,
                description="Event flow has changed",
                rule_name="signal_detector",
                node_ids=model.event_changes,
            )
            signals.append(signal)
        
        return signals
    
    def _detect_transaction_changes(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> List[Signal]:
        """Detect transaction boundary changes."""
        signals = []
        
        # Find transaction nodes
        transaction_nodes = [
            node_id for node_id, node in graph.nodes.items()
            if node.node_type == NodeType.TRANSACTION
        ]
        
        if transaction_nodes:
            signal = Signal(
                signal_id="signal_transaction_boundary_changed",
                name="TRANSACTION_BOUNDARY_CHANGED",
                category=SignalCategory.TRANSACTION,
                description="Transaction boundary has changed",
                rule_name="signal_detector",
                node_ids=transaction_nodes,
            )
            signals.append(signal)
        
        return signals
    
    def _detect_no_test_coverage(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> List[Signal]:
        """Detect nodes with no reachable test."""
        signals = []
        
        if model.coverage:
            # Find uncovered nodes
            uncovered = []
            for node_id in graph.nodes:
                # Simple heuristic: if node is not a test and not covered
                node = graph.nodes[node_id]
                if node.node_type not in (NodeType.TEST, NodeType.MIGRATION):
                    uncovered.append(node_id)
            
            if uncovered:
                signal = Signal(
                    signal_id="signal_no_reachable_test",
                    name="NO_REACHABLE_TEST",
                    category=SignalCategory.COVERAGE,
                    description="Nodes with no reachable test",
                    rule_name="signal_detector",
                    node_ids=uncovered,
                )
                signals.append(signal)
        
        return signals
    
    def _detect_external_service_changes(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> List[Signal]:
        """Detect external service changes."""
        signals = []
        
        if model.external_service_calls:
            signal = Signal(
                signal_id="signal_external_service_changed",
                name="EXTERNAL_SERVICE_CHANGED",
                category=SignalCategory.EXTERNAL,
                description="External service interface has changed",
                rule_name="signal_detector",
                node_ids=model.external_service_calls,
            )
            signals.append(signal)
        
        return signals
    
    def _detect_cache_changes(
        self, graph: SemanticGraph, model: KnowledgeModel
    ) -> List[Signal]:
        """Detect cache path changes."""
        signals = []
        
        if model.cache_changes:
            signal = Signal(
                signal_id="signal_cache_path_changed",
                name="CACHE_PATH_CHANGED",
                category=SignalCategory.CACHE,
                description="Cache path has changed",
                rule_name="signal_detector",
                node_ids=model.cache_changes,
            )
            signals.append(signal)
        
        return signals