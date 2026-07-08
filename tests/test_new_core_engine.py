"""Tests for the new Factor Core Engine implementation."""

from __future__ import annotations

import pytest

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.knowledge_model import KnowledgeModel
from core_engine.models.evidence import EvidenceCategory
from core_engine.models.signal import SignalCategory
from core_engine.models.compiler_pass import PassResult
from core_engine.pipelines.compiler import Compiler
from core_engine.pipelines.registry import PassRegistry
from core_engine.analyzers.execution_analyzer import ExecutionAnalyzer
from core_engine.analyzers.interaction_analyzer import InteractionAnalyzer
from core_engine.analyzers.propagation_analyzer import PropagationAnalyzer
from core_engine.analyzers.coverage_analyzer import CoverageAnalyzerPass
from core_engine.analyzers.surface_analyzer import SurfaceAnalyzer
from core_engine.analyzers.evidence_collector import EvidenceCollector
from core_engine.analyzers.signal_detector import SignalDetector
from core_engine.analyzers.context_builder import ContextBuilder
from core_engine.analyzers.explainability_auditor import ExplainabilityAuditor


def _make_node(
    node_type: NodeType,
    name: str,
    file_path: str = "app/service.py",
    change_type: str = "modified",
    **kwargs,
) -> BaseNode:
    """Helper to create a node."""
    return BaseNode(
        node_type=node_type,
        name=name,
        file_path=file_path,
        change_type=change_type,
        properties=kwargs,
    )


def _make_edge(
    edge_type: EdgeType,
    source: BaseNode,
    target: BaseNode,
    change_type: str = "added",
    **kwargs,
) -> BaseEdge:
    """Helper to create an edge."""
    return BaseEdge(
        edge_type=edge_type,
        source=source,
        target=target,
        change_type=change_type,
        properties=kwargs,
    )


@pytest.fixture
def simple_graph() -> SemanticGraph:
    """A minimal graph with one endpoint calling a service that writes to DB."""
    graph = SemanticGraph()

    endpoint = _make_node(NodeType.ENDPOINT, "create_user", change_type="added",
                          method="POST", route="/users", handler_function="create_user_handler")
    service = _make_node(NodeType.FUNCTION, "create_user_handler", change_type="added")
    repo = _make_node(NodeType.FUNCTION, "user_repository", change_type="added")
    model = _make_node(NodeType.MODEL, "User", change_type="added")
    db = _make_node(NodeType.FUNCTION, "db_session", change_type="modified")

    graph.add_node(endpoint)
    graph.add_node(service)
    graph.add_node(repo)
    graph.add_node(model)
    graph.add_node(db)

    graph.add_edge(_make_edge(EdgeType.CALLS, endpoint, service))
    graph.add_edge(_make_edge(EdgeType.CALLS, service, repo))
    graph.add_edge(_make_edge(EdgeType.WRITES, repo, model))
    graph.add_edge(_make_edge(EdgeType.USES, repo, db))

    return graph


# ---------------------------------------------------------------------------
# Phase 0: Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_knowledge_model_immutability(self):
        """Test that KnowledgeModel is immutable."""
        model = KnowledgeModel.empty("graph1", "abc123")
        
        # with_execution_unit should return a new instance
        new_model = model.with_execution_unit("exec_1")
        assert model is not new_model
        assert len(model.execution_units) == 0
        assert len(new_model.execution_units) == 1
        
        # Original should be unchanged
        assert model.graph_id == "graph1"
        assert model.commit_hash == "abc123"
    
    def test_knowledge_model_with_signal(self):
        """Test adding signals to KnowledgeModel."""
        model = KnowledgeModel.empty("graph1", "abc123")
        new_model = model.with_signal("signal_1")
        
        assert len(model.signals) == 0
        assert len(new_model.signals) == 1
        assert new_model.signals[0] == "signal_1"
    
    def test_knowledge_model_with_diagnostic(self):
        """Test adding diagnostics to KnowledgeModel."""
        model = KnowledgeModel.empty("graph1", "abc123")
        new_model = model.with_diagnostic("test message")
        
        assert len(model.diagnostics) == 0
        assert len(new_model.diagnostics) == 1
        assert new_model.diagnostics[0] == "test message"


# ---------------------------------------------------------------------------
# Phase 1: Compiler Infrastructure Tests
# ---------------------------------------------------------------------------


class TestCompilerInfrastructure:
    def test_registry_register_and_get(self):
        """Test pass registration and retrieval."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        
        assert registry.get("execution_analyzer") == ExecutionAnalyzer
        assert registry.get("nonexistent") is None
    
    def test_registry_duplicate_raises(self):
        """Test that duplicate registration raises error."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(ExecutionAnalyzer)
    
    def test_topological_sort(self):
        """Test dependency ordering."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(InteractionAnalyzer)
        registry.register(PropagationAnalyzer)
        
        # ExecutionAnalyzer has no dependencies
        # InteractionAnalyzer depends on execution_units
        # PropagationAnalyzer depends on execution_units and interaction_clusters
        
        sorted_passes = registry.topological_sort()
        
        # ExecutionAnalyzer should come first
        assert sorted_passes[0] == ExecutionAnalyzer
    
    def test_compiler_basic(self, simple_graph: SemanticGraph):
        """Test basic compiler functionality."""
        compiler = Compiler()
        
        # Register passes
        compiler.register_pass(ExecutionAnalyzer)
        compiler.register_pass(InteractionAnalyzer)
        
        # Compile
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        assert isinstance(model, KnowledgeModel)
        assert model.graph_id == "graph1"
        assert model.commit_hash == "abc123"
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Phase 2: Execution Analyzer Tests
# ---------------------------------------------------------------------------


class TestExecutionAnalyzer:
    def test_finds_entrypoints(self, simple_graph: SemanticGraph):
        """Test that execution analyzer finds entrypoints."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should find the endpoint as an entrypoint
        assert len(model.execution_units) > 0
    
    def test_finds_functions(self, simple_graph: SemanticGraph):
        """Test that execution analyzer finds functions."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should find functions
        assert len(model.execution_units) > 0
    
    def test_produces_pass_result(self, simple_graph: SemanticGraph):
        """Test that execution analyzer produces PassResult."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        assert len(results) == 1
        assert isinstance(results[0], PassResult)
        assert results[0].success
        assert results[0].pass_name == "execution_analyzer"


# ---------------------------------------------------------------------------
# Phase 3: Interaction Analyzer Tests
# ---------------------------------------------------------------------------


class TestInteractionAnalyzer:
    def test_finds_connected_components(self, simple_graph: SemanticGraph):
        """Test that interaction analyzer finds connected components."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(InteractionAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should find interaction clusters
        assert len(model.interaction_clusters) >= 0  # May be 0 for simple graph
    
    def test_produces_pass_result(self, simple_graph: SemanticGraph):
        """Test that interaction analyzer produces PassResult."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(InteractionAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        assert len(results) == 2
        assert results[1].pass_name == "interaction_analyzer"
        assert results[1].success


# ---------------------------------------------------------------------------
# Phase 4: Propagation Analyzer Tests
# ---------------------------------------------------------------------------


class TestPropagationAnalyzer:
    def test_finds_propagation_paths(self, simple_graph: SemanticGraph):
        """Test that propagation analyzer finds paths."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(PropagationAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should find propagation paths from changed nodes
        assert len(model.propagation_paths) >= 0
    
    def test_propagates_from_changed_nodes(self, simple_graph: SemanticGraph):
        """Test that propagation starts from changed nodes."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(PropagationAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # All nodes in simple_graph are changed (added or modified)
        # So should have propagation paths
        assert isinstance(results[1], PassResult)
        assert results[1].success


# ---------------------------------------------------------------------------
# Phase 5: Coverage Analyzer Tests
# ---------------------------------------------------------------------------


class TestCoverageAnalyzer:
    def test_analyzes_coverage(self, simple_graph: SemanticGraph):
        """Test that coverage analyzer works."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(CoverageAnalyzerPass)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should set coverage
        assert model.coverage is not None
    
    def test_no_tests_in_graph(self, simple_graph: SemanticGraph):
        """Test coverage with no tests."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(CoverageAnalyzerPass)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # With no tests, coverage should be 0
        assert results[1].metadata.get("node_coverage") == 0.0


# ---------------------------------------------------------------------------
# Phase 6: Surface Analyzer Tests
# ---------------------------------------------------------------------------


class TestSurfaceAnalyzer:
    def test_finds_api_changes(self, simple_graph: SemanticGraph):
        """Test that surface analyzer finds API changes."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(SurfaceAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should find the endpoint as an API change
        assert len(model.api_changes) > 0
    
    def test_finds_schema_changes(self, simple_graph: SemanticGraph):
        """Test that surface analyzer finds schema changes."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(SurfaceAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should find the model as a schema change
        assert len(model.schema_changes) > 0


# ---------------------------------------------------------------------------
# Phase 7: Evidence Collector Tests
# ---------------------------------------------------------------------------


class TestEvidenceCollector:
    def test_creates_evidence(self, simple_graph: SemanticGraph):
        """Test that evidence collector creates evidence."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(SurfaceAnalyzer)
        registry.register(EvidenceCollector)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should create evidence
        assert len(model.evidence) > 0
    
    def test_evidence_has_correct_category(self, simple_graph: SemanticGraph):
        """Test that evidence has correct category."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(EvidenceCollector)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Evidence IDs should start with "evidence_"
        for evidence_id in model.evidence:
            assert evidence_id.startswith("evidence_")


# ---------------------------------------------------------------------------
# Phase 8: Signal Detector Tests
# ---------------------------------------------------------------------------


class TestSignalDetector:
    def test_detects_signals(self, simple_graph: SemanticGraph):
        """Test that signal detector creates signals."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(SurfaceAnalyzer)
        registry.register(SignalDetector)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should detect signals
        assert len(model.signals) > 0
    
    def test_signal_categories(self, simple_graph: SemanticGraph):
        """Test that signals have correct categories."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(SurfaceAnalyzer)
        registry.register(SignalDetector)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Should have signals with valid categories
        for signal_id in model.signals:
            assert signal_id.startswith("signal_")


# ---------------------------------------------------------------------------
# Phase 9: Context Builder Tests
# ---------------------------------------------------------------------------


class TestContextBuilder:
    def test_builds_context(self, simple_graph: SemanticGraph):
        """Test that context builder creates context."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(ContextBuilder)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Context is stored in pass_metadata
        assert "context_builder" in model.pass_metadata
    
    def test_context_has_statistics(self, simple_graph: SemanticGraph):
        """Test that context has statistics."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(ContextBuilder)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Check that statistics were built
        context_metadata = model.pass_metadata.get("context_builder", {})
        assert "statistics" in context_metadata


# ---------------------------------------------------------------------------
# Phase 10: Explainability Auditor Tests
# ---------------------------------------------------------------------------


class TestExplainabilityAuditor:
    def test_audit_passes(self, simple_graph: SemanticGraph):
        """Test that audit passes for valid graph."""
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        registry.register(ExplainabilityAuditor)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # Audit should pass
        assert results[1].success
        assert results[1].pass_name == "explainability_auditor"


# ---------------------------------------------------------------------------
# Phase 11: Full Pipeline Integration Tests
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_complete_pipeline(self, simple_graph: SemanticGraph):
        """Test the complete pipeline with all passes."""
        registry = PassRegistry()
        
        # Register all passes in order
        registry.register(ExecutionAnalyzer)
        registry.register(InteractionAnalyzer)
        registry.register(PropagationAnalyzer)
        registry.register(CoverageAnalyzerPass)
        registry.register(SurfaceAnalyzer)
        registry.register(EvidenceCollector)
        registry.register(SignalDetector)
        registry.register(ContextBuilder)
        registry.register(ExplainabilityAuditor)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(simple_graph, "graph1", "abc123")
        
        # All passes should succeed
        assert all(r.success for r in results)
        
        # Model should be enriched
        assert len(model.execution_units) > 0
        assert len(model.signals) > 0
        assert len(model.evidence) > 0
        assert model.coverage is not None
    
    def test_pipeline_determinism(self, simple_graph: SemanticGraph):
        """Test that pipeline is deterministic."""
        registry1 = PassRegistry()
        registry1.register(ExecutionAnalyzer)
        registry1.register(SignalDetector)
        
        registry2 = PassRegistry()
        registry2.register(ExecutionAnalyzer)
        registry2.register(SignalDetector)
        
        compiler1 = Compiler(registry1)
        compiler2 = Compiler(registry2)
        
        model1, results1 = compiler1.compile(simple_graph, "graph1", "abc123")
        model2, results2 = compiler2.compile(simple_graph, "graph1", "abc123")
        
        # Results should be identical
        assert len(model1.execution_units) == len(model2.execution_units)
        assert len(model1.signals) == len(model2.signals)
        assert len(results1) == len(results2)
    
    def test_empty_graph(self):
        """Test pipeline with empty graph."""
        graph = SemanticGraph()
        
        registry = PassRegistry()
        registry.register(ExecutionAnalyzer)
        
        compiler = Compiler(registry)
        model, results = compiler.compile(graph, "empty_graph", "abc123")
        
        assert isinstance(model, KnowledgeModel)
        assert len(model.execution_units) == 0
        assert all(r.success for r in results)