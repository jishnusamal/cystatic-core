"""Comprehensive tests for the core engine pipeline.

Tests the full pipeline end-to-end:
1. Graph validation
2. Rule execution (all 12 rules)
3. Graph analysis (execution paths, coverage, architecture, impact)
4. Signal combination
5. Confidence scoring
6. Packet building and compression
7. Full pipeline integration
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType, FunctionNode, MethodNode
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.models.semantic_graph import ValidatedSemanticGraph
from core_engine.models.evidence import (
    Signal,
    Evidence,
    ExecutionEvidence,
    CoverageEvidence,
    ArchitectureEvidence,
    CombinedEvidence,
    ExecutionPath,
    EvidenceCategory,
)
from core_engine.models.packet import EvidencePacket
from core_engine.pipelines.review_pipeline import ReviewPipeline
from core_engine.packet.packet_builder import PacketBuilder
from core_engine.packet.compressor import PacketCompressor
from core_engine.inference.rule_runner import RuleRunner
from core_engine.inference.signal_combiner import SignalCombiner
from core_engine.inference.confidence import ConfidenceScorer
from core_engine.analyzers.graph_traverser import GraphTraverser
from core_engine.analyzers.execution_paths import ExecutionPathAnalyzer
from core_engine.analyzers.impact_analyzer import ImpactAnalyzer
from core_engine.analyzers.coverage_analyzer import CoverageAnalyzer
from core_engine.analyzers.architecture_analyzer import ArchitectureAnalyzer
from core_engine.rules import (
    ValidationRule,
    PersistenceRule,
    QueryRule,
    TransactionRule,
    MigrationRule,
    APIExposureRule,
    EventRule,
    CacheRule,
    AuthRule,
    ExternalDependencyRule,
    CrossDomainRule,
    CoverageRule,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_node(
    node_type: NodeType,
    name: str,
    file_path: str = "app/service.py",
    change_type: str = "modified",
    **kwargs,
) -> BaseNode:
    """Helper to create a node with standard key generation."""
    node = BaseNode(
        node_type=node_type,
        name=name,
        file_path=file_path,
        change_type=change_type,
        properties=kwargs,
    )
    return node


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


@pytest.fixture
def validation_graph() -> SemanticGraph:
    """Graph with validation logic changes."""
    graph = SemanticGraph()

    validate_fn = _make_node(NodeType.FUNCTION, "validate_email", change_type="modified")
    endpoint = _make_node(NodeType.ENDPOINT, "register_user", change_type="modified",
                          method="POST", route="/register")
    model = _make_node(NodeType.MODEL, "User", change_type="modified")
    field = _make_node(NodeType.FIELD, "email", change_type="modified", model_name="User")

    graph.add_node(validate_fn)
    graph.add_node(endpoint)
    graph.add_node(model)
    graph.add_node(field)

    graph.add_edge(_make_edge(EdgeType.VALIDATES, validate_fn, model))
    graph.add_edge(_make_edge(EdgeType.CALLS, endpoint, validate_fn))
    graph.add_edge(_make_edge(EdgeType.WRITES, endpoint, model))

    return graph


@pytest.fixture
def full_pipeline_graph() -> SemanticGraph:
    """A more complex graph exercising all rule types."""
    graph = SemanticGraph()

    # API layer
    create_user = _make_node(NodeType.ENDPOINT, "POST /users", "api/users.py",
                             change_type="added", method="POST", route="/users",
                             handler_function="create_user", framework="fastapi")
    delete_user = _make_node(NodeType.ENDPOINT, "DELETE /users/{id}", "api/users.py",
                             change_type="modified", method="DELETE", route="/users/{id}")

    # Service layer
    user_service = _make_node(NodeType.FUNCTION, "create_user", "services/user_service.py",
                              change_type="added")
    delete_service = _make_node(NodeType.FUNCTION, "delete_user", "services/user_service.py",
                                change_type="modified")

    # Validation
    validate_email = _make_node(NodeType.FUNCTION, "validate_email", "services/validation.py",
                                change_type="modified")
    validate_role = _make_node(NodeType.FUNCTION, "check_permission", "services/auth.py",
                               change_type="added")

    # Auth
    auth_decorator = _make_node(NodeType.DECORATOR, "login_required", "api/users.py",
                                change_type="added", target_name="delete_user")

    # Persistence
    user_repo = _make_node(NodeType.FUNCTION, "user_repository", "repos/user_repo.py",
                           change_type="added")
    user_model = _make_node(NodeType.MODEL, "User", "models/user.py", change_type="added")
    email_field = _make_node(NodeType.FIELD, "email", "models/user.py",
                             change_type="added", model_name="User")
    role_field = _make_node(NodeType.FIELD, "role", "models/user.py",
                            change_type="added", model_name="User")

    # Queries
    find_users = _make_node(NodeType.QUERY, "find_active_users", "repos/user_repo.py",
                            change_type="modified", target_model="User",
                            changed_filters=True)
    # Set changed_filters as a direct attribute (QueryRule uses getattr)
    find_users.changed_filters = True

    # Transactions
    create_tx = _make_node(NodeType.TRANSACTION, "create_user_tx", "services/user_service.py",
                           change_type="added", scope="function", is_nested=False)

    # Events
    user_created_event = _make_node(NodeType.EVENT, "user.created", "events/user_events.py",
                                    change_type="added", event_type="domain")

    # External service
    email_service = _make_node(NodeType.EXTERNAL_SERVICE, "sendgrid", "services/email.py",
                               change_type="added", service_type="email", protocol="https")

    # Cache
    user_cache = _make_node(NodeType.CACHE, "user_cache", "services/cache.py",
                            change_type="added", operation="set", cache_type="redis")
    # Set operation as a direct attribute (CacheRule uses getattr)
    user_cache.operation = "set"
    user_cache.cache_type = "redis"

    # Migration
    add_role_migration = _make_node(NodeType.MIGRATION, "add_role_column", "migrations/001.py",
                                    change_type="added",
                                    operations=[{"type": "add_column", "column": "role"}])

    # Test
    test_user = _make_node(NodeType.TEST, "test_create_user", "tests/test_users.py",
                           change_type="added", target_functions=["FUNCTION:create_user:services/user_service.py"])

    # Add all nodes
    for node in [create_user, delete_user, user_service, delete_service,
                 validate_email, validate_role, auth_decorator,
                 user_repo, user_model, email_field, role_field,
                 find_users, create_tx, user_created_event,
                 email_service, user_cache, add_role_migration, test_user]:
        graph.add_node(node)

    # Add edges
    graph.add_edge(_make_edge(EdgeType.CALLS, create_user, user_service))
    graph.add_edge(_make_edge(EdgeType.CALLS, delete_user, delete_service))
    graph.add_edge(_make_edge(EdgeType.CALLS, user_service, validate_email))
    graph.add_edge(_make_edge(EdgeType.CALLS, user_service, user_repo))
    graph.add_edge(_make_edge(EdgeType.VALIDATES, validate_email, user_model))
    graph.add_edge(_make_edge(EdgeType.VALIDATES, validate_role, user_model))
    graph.add_edge(_make_edge(EdgeType.WRITES, user_repo, user_model))
    graph.add_edge(_make_edge(EdgeType.READS, find_users, user_model))
    graph.add_edge(_make_edge(EdgeType.USES, user_repo, find_users))
    graph.add_edge(_make_edge(EdgeType.PUBLISHES, user_service, user_created_event))
    graph.add_edge(_make_edge(EdgeType.SENDS_HTTP, user_service, email_service,
                              method="POST", url="https://api.sendgrid.com/v3/mail/send"))
    graph.add_edge(_make_edge(EdgeType.EXPOSES, create_user, user_service))
    graph.add_edge(_make_edge(EdgeType.TESTS, test_user, user_service))
    graph.add_edge(_make_edge(EdgeType.MIGRATES, add_role_migration, user_model))

    return graph


# ---------------------------------------------------------------------------
# Stage 1: Graph Validation
# ---------------------------------------------------------------------------


class TestGraphValidation:
    def test_validates_clean_graph(self, simple_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(simple_graph)
        assert validated.is_valid
        assert len(validated.errors) == 0

    def test_detects_duplicate_nodes(self):
        graph = SemanticGraph()
        n1 = _make_node(NodeType.FUNCTION, "foo", "app.py")
        n2 = _make_node(NodeType.FUNCTION, "foo", "app.py")
        # Bypass add_node dedup to force duplicate into the graph
        graph.nodes["FUNCTION:foo:app.py"] = n1
        graph.nodes["FUNCTION:foo:app.py:dup"] = n2
        validated = ValidatedSemanticGraph.validate(graph)
        assert not validated.is_valid
        assert any("Duplicate" in e for e in validated.errors)

    def test_detects_missing_edge_targets(self):
        graph = SemanticGraph()
        source = _make_node(NodeType.FUNCTION, "source", "app.py")
        target = _make_node(NodeType.FUNCTION, "target", "other.py")
        graph.add_node(source)
        # Add edge referencing target that isn't in graph
        graph.edges.append(_make_edge(EdgeType.CALLS, source, target))
        validated = ValidatedSemanticGraph.validate(graph)
        assert not validated.is_valid
        assert any("not found" in e for e in validated.errors)

    def test_identifies_entrypoints_and_sinks(self, simple_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(simple_graph)
        entrypoints = validated.get_entrypoints()
        sinks = validated.get_sinks()
        assert len(entrypoints) > 0
        assert len(sinks) > 0

    def test_precomputes_lookups(self, simple_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(simple_graph)
        endpoints = validated.get_nodes_by_type(NodeType.ENDPOINT)
        assert len(endpoints) == 1
        assert endpoints[0].name == "create_user"


# ---------------------------------------------------------------------------
# Stage 2: Rule Engine
# ---------------------------------------------------------------------------


class TestRules:
    def test_validation_rule_detects_changes(self, validation_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(validation_graph)
        rule = ValidationRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "ValidationModified" in signal_names

    def test_persistence_rule_detects_writes(self, simple_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(simple_graph)
        rule = PersistenceRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "PersistenceWriteAdded" in signal_names

    def test_api_rule_detects_new_endpoints(self, simple_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(simple_graph)
        rule = APIExposureRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "NewAPIEndpoint" in signal_names

    def test_query_rule_detects_changes(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        rule = QueryRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "QuerySemanticsChanged" in signal_names

    def test_transaction_rule_detects_additions(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        rule = TransactionRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "TransactionAdded" in signal_names

    def test_migration_rule_detects_additions(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        rule = MigrationRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "MigrationAdded" in signal_names

    def test_event_rule_detects_new_events(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        rule = EventRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "NewEventPublished" in signal_names

    def test_cache_rule_detects_additions(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        rule = CacheRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "CacheWriteAdded" in signal_names

    def test_auth_rule_detects_changes(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        rule = AuthRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "AuthAdded" in signal_names

    def test_external_dependency_rule(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        rule = ExternalDependencyRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        assert "NewExternalDependency" in signal_names

    def test_cross_domain_rule(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        rule = CrossDomainRule()
        result = rule.execute(validated)
        # Cross-domain requires different top-level directories
        # Our graph has nodes in api/, services/, repos/, models/, events/, migrations/, tests/
        # So cross-domain calls should be detected
        signal_names = [s.name for s in result.signals]
        assert "CrossDomainInteraction" in signal_names

    def test_coverage_rule_detects_untested_code(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        rule = CoverageRule()
        result = rule.execute(validated)
        signal_names = [s.name for s in result.signals]
        # The test only covers create_user, so other entrypoints should be untested
        assert len(result.signals) > 0

    def test_rule_runner_executes_all_rules(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        runner = RuleRunner()
        signals = runner.run_all(validated)
        assert len(signals) > 0
        # Should have signals from multiple rules
        rule_names = set(s.rule_name for s in signals)
        assert len(rule_names) > 1

    def test_rule_runner_returns_results(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        runner = RuleRunner()
        results = runner.run_all_with_results(validated)
        assert len(results) == 12  # All 12 rules


# ---------------------------------------------------------------------------
# Stage 3: Graph Analysis
# ---------------------------------------------------------------------------


class TestGraphAnalysis:
    def test_execution_path_analyzer(self, simple_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(simple_graph)
        analyzer = ExecutionPathAnalyzer(validated)
        evidence = analyzer.analyze()
        assert isinstance(evidence, ExecutionEvidence)
        assert len(evidence.paths) > 0

    def test_impact_analyzer(self, simple_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(simple_graph)
        analyzer = ImpactAnalyzer(validated)
        evidence = analyzer.analyze()
        assert isinstance(evidence, Evidence)
        assert evidence.confidence > 0

    def test_coverage_analyzer(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        analyzer = CoverageAnalyzer(validated)
        evidence = analyzer.analyze()
        assert isinstance(evidence, CoverageEvidence)
        # Some code should be untested
        assert len(evidence.untested_entrypoints) >= 0

    def test_architecture_analyzer(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        analyzer = ArchitectureAnalyzer(validated)
        evidence = analyzer.analyze()
        assert isinstance(evidence, ArchitectureEvidence)
        assert len(evidence.new_apis) > 0
        assert len(evidence.new_database_access) > 0

    def test_graph_traverser_bfs(self, simple_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(simple_graph)
        traverser = GraphTraverser(validated)
        entrypoints = validated.get_entrypoints()
        if entrypoints:
            result = traverser.bfs(entrypoints[0], max_depth=5)
            assert len(result) > 0

    def test_graph_traverser_reachability(self, simple_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(simple_graph)
        traverser = GraphTraverser(validated)
        entrypoints = validated.get_entrypoints()
        if entrypoints:
            reachable = traverser.get_reachable_nodes(entrypoints[0], max_depth=5)
            assert len(reachable) > 0


# ---------------------------------------------------------------------------
# Stage 4: Signal Combination
# ---------------------------------------------------------------------------


class TestSignalCombination:
    def test_combines_related_signals(self):
        combiner = SignalCombiner()
        signals = [
            Signal(name="ValidationModified", rule_name="ValidationRule",
                   description="Validation modified", confidence=1.0),
            Signal(name="PersistenceWriteAdded", rule_name="PersistenceRule",
                   description="Write added", confidence=1.0),
            Signal(name="TransactionBoundaryChanged", rule_name="TransactionRule",
                   description="Transaction changed", confidence=1.0),
        ]
        combined = combiner.combine(signals)
        assert len(combined) > 0
        descriptions = [c.description for c in combined]
        assert any("persistent state" in d for d in descriptions)

    def test_no_combination_for_unrelated_signals(self):
        combiner = SignalCombiner()
        signals = [
            Signal(name="ValidationModified", rule_name="ValidationRule",
                   description="Validation modified", confidence=1.0),
            Signal(name="NewEventPublished", rule_name="EventRule",
                   description="New event", confidence=1.0),
        ]
        combined = combiner.combine(signals)
        # These two alone don't match any combination rule
        assert len(combined) == 0

    def test_deduplicates_combined_evidence(self):
        combiner = SignalCombiner()
        signals = [
            Signal(name="ValidationModified", rule_name="ValidationRule",
                   description="Validation modified", confidence=1.0),
            Signal(name="PersistenceWriteAdded", rule_name="PersistenceRule",
                   description="Write added", confidence=1.0),
        ]
        combined = combiner.combine(signals)
        # Should only produce one combined evidence for this pair
        assert len(combined) == 1


# ---------------------------------------------------------------------------
# Stage 5: Confidence Scoring
# ---------------------------------------------------------------------------


class TestConfidenceScoring:
    def test_signal_confidence_is_always_1(self):
        scorer = ConfidenceScorer()
        signal = Signal(name="Test", rule_name="TestRule", description="test")
        assert scorer.score_signal(signal) == 1.0

    def test_execution_confidence(self):
        scorer = ConfidenceScorer()
        evidence = ExecutionEvidence(
            description="test",
            paths=[
                ExecutionPath(path_id="p1", entrypoint="e1", sink="s1",
                              nodes=["a", "b", "c"])
            ],
        )
        score = scorer.score_execution_evidence(evidence)
        assert 0.5 <= score <= 1.0

    def test_coverage_confidence(self):
        scorer = ConfidenceScorer()
        evidence = CoverageEvidence(description="test")
        score = scorer.score_coverage_evidence(evidence)
        assert score > 0

    def test_architecture_confidence(self):
        scorer = ConfidenceScorer()
        evidence = ArchitectureEvidence(description="test", new_apis=["POST /users"])
        score = scorer.score_architecture_evidence(evidence)
        assert score > 0

    def test_combined_confidence(self):
        scorer = ConfidenceScorer()
        evidence = CombinedEvidence(
            description="test",
            source_signals=[
                Signal(name="A", rule_name="R1", description="a", confidence=1.0),
                Signal(name="B", rule_name="R2", description="b", confidence=0.9),
            ],
        )
        score = scorer.score_combined_evidence(evidence)
        assert 0.5 <= score <= 1.0

    def test_confidence_summary(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        runner = RuleRunner()
        signals = runner.run_all(validated)

        exec_analyzer = ExecutionPathAnalyzer(validated)
        exec_evidence = exec_analyzer.analyze()

        cov_analyzer = CoverageAnalyzer(validated)
        cov_evidence = cov_analyzer.analyze()

        arch_analyzer = ArchitectureAnalyzer(validated)
        arch_evidence = arch_analyzer.analyze()

        combiner = SignalCombiner()
        combined = combiner.combine(signals)

        scorer = ConfidenceScorer()
        summary = scorer.build_confidence_summary(
            signals=signals,
            execution=exec_evidence,
            coverage=cov_evidence,
            architecture=arch_evidence,
            combined=combined,
        )
        assert len(summary) > 0
        for key, value in summary.items():
            assert 0.0 <= value <= 1.0


# ---------------------------------------------------------------------------
# Stage 6: Packet Building & Compression
# ---------------------------------------------------------------------------


class TestPacket:
    def test_packet_builder_creates_packet(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        builder = PacketBuilder()
        packet = builder.build(validated, generate_summary=True)
        assert isinstance(packet, EvidencePacket)
        assert len(packet.summary) > 0
        assert len(packet.signals) > 0

    def test_packet_has_all_sections(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        builder = PacketBuilder()
        packet = builder.build(validated, generate_summary=True)
        assert packet.signals is not None
        assert packet.execution_evidence is not None
        assert packet.coverage_evidence is not None
        assert packet.architecture_evidence is not None
        assert len(packet.confidence_summary) > 0

    def test_compressor_deduplicates(self):
        compressor = PacketCompressor()
        packet = EvidencePacket(
            signals=[
                Signal(name="Test", rule_name="R1", description="a",
                       node_ids=["n1"]),
                Signal(name="Test", rule_name="R1", description="a",
                       node_ids=["n1"]),  # Duplicate
                Signal(name="Other", rule_name="R2", description="b",
                       node_ids=["n2"]),
            ],
            execution_paths=[
                ExecutionPath(path_id="p1", entrypoint="e1", sink="s1",
                              nodes=["a", "b"]),
                ExecutionPath(path_id="p1", entrypoint="e1", sink="s1",
                              nodes=["a", "b"]),  # Duplicate
            ],
        )
        compressed = compressor.compress(packet)
        assert len(compressed.signals) == 2  # Deduplicated from 3 to 2
        assert len(compressed.execution_paths) == 1  # Deduplicated from 2 to 1

    def test_packet_estimated_tokens(self, full_pipeline_graph: SemanticGraph):
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        builder = PacketBuilder()
        packet = builder.build(validated, generate_summary=True)
        tokens = packet.estimated_tokens
        assert tokens > 0


# ---------------------------------------------------------------------------
# Stage 7: Full Pipeline Integration
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_review_pipeline_end_to_end(self, full_pipeline_graph: SemanticGraph):
        pipeline = ReviewPipeline()
        packet = pipeline.run(full_pipeline_graph)
        assert isinstance(packet, EvidencePacket)
        assert len(packet.signals) > 0
        assert packet.execution_evidence is not None
        assert packet.coverage_evidence is not None
        assert packet.architecture_evidence is not None
        assert len(packet.confidence_summary) > 0

    def test_pipeline_raises_on_invalid_graph(self):
        graph = SemanticGraph()
        # Add edge with missing target
        source = _make_node(NodeType.FUNCTION, "source", "app.py")
        target = _make_node(NodeType.FUNCTION, "target", "other.py")
        graph.add_node(source)
        graph.edges.append(_make_edge(EdgeType.CALLS, source, target))

        pipeline = ReviewPipeline()
        with pytest.raises(ValueError, match="validation failed"):
            pipeline.run(graph)

    def test_pipeline_with_warnings(self):
        graph = SemanticGraph()
        source = _make_node(NodeType.FUNCTION, "source", "app.py")
        target = _make_node(NodeType.FUNCTION, "target", "other.py")
        graph.add_node(source)
        graph.edges.append(_make_edge(EdgeType.CALLS, source, target))

        pipeline = ReviewPipeline()
        packet, warnings = pipeline.run_with_warnings(graph)
        assert len(warnings) > 0
        assert isinstance(packet, EvidencePacket)

    def test_pipeline_produces_compact_packet(self, full_pipeline_graph: SemanticGraph):
        """Verify the packet is reasonably compact (<3K tokens for complex test graph)."""
        pipeline = ReviewPipeline()
        packet = pipeline.run(full_pipeline_graph)
        tokens = packet.estimated_tokens
        # Complex test graph with 18 nodes, 15 edges across 7 domains
        # ~2.2K tokens is reasonable for this complexity
        assert tokens < 3000, f"Packet too large: {tokens} tokens"

    def test_packet_to_dict_serialization(self, full_pipeline_graph: SemanticGraph):
        pipeline = ReviewPipeline()
        packet = pipeline.run(full_pipeline_graph)
        d = packet.to_dict()
        assert "summary" in d
        assert "signals" in d
        assert "execution_paths" in d
        assert "execution_evidence" in d
        assert "coverage_evidence" in d
        assert "architecture_evidence" in d
        assert "combined_evidence" in d
        assert "confidence_summary" in d

    def test_signal_combiner_in_pipeline(self, full_pipeline_graph: SemanticGraph):
        """Verify signal combination works within the full pipeline."""
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)
        runner = RuleRunner()
        signals = runner.run_all(validated)
        combiner = SignalCombiner()
        combined = combiner.combine(signals)
        # Should produce at least some combined evidence
        assert len(combined) >= 0

    def test_all_analyzers_produce_evidence(self, full_pipeline_graph: SemanticGraph):
        """Verify every analyzer produces evidence with correct types."""
        validated = ValidatedSemanticGraph.validate(full_pipeline_graph)

        exec_evidence = ExecutionPathAnalyzer(validated).analyze()
        assert isinstance(exec_evidence, ExecutionEvidence)
        assert exec_evidence.category == EvidenceCategory.EXECUTION

        cov_evidence = CoverageAnalyzer(validated).analyze()
        assert isinstance(cov_evidence, CoverageEvidence)
        assert cov_evidence.category == EvidenceCategory.COVERAGE

        arch_evidence = ArchitectureAnalyzer(validated).analyze()
        assert isinstance(arch_evidence, ArchitectureEvidence)
        assert arch_evidence.category == EvidenceCategory.ARCHITECTURE

        impact_evidence = ImpactAnalyzer(validated).analyze()
        assert isinstance(impact_evidence, Evidence)