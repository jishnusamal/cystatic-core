"""Tests for the Behavior Graph v2 pipeline.

Tests all 10 agents and the full pipeline.
"""

from __future__ import annotations

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.ir.nodes import BaseNode, NodeType
from language_adapters.ir.edges import BaseEdge, EdgeType

from core_engine.behavior_graph import (
    BehaviorGraphPipeline,
    PipelineResult,
    ComponentBuilder,
    RepositoryInterpreter,
    CapabilityExtractor,
    ResponsibilityBuilder,
    DependencyBuilder,
    DomainMapper,
    ChangeAnalyzer,
    StableFactFilter,
    BehaviorGraphBuilder,
    DeterministicImpactEngine,
    Component,
    ComponentType,
    Domain,
    Capability,
    Responsibility,
    BehaviorEdge,
    BehaviorEdgeType,
    BehaviorGraph,
    ChangeDelta,
    DeltaType,
    ImpactResult,
)


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
    **kwargs,
) -> BaseEdge:
    """Helper to create an edge."""
    return BaseEdge(
        edge_type=edge_type,
        source=source,
        target=target,
        properties=kwargs,
    )


# ===== Tests for Models =====


def test_component_creation():
    """Test that a Component can be created with all fields."""
    component = Component(
        id="CheckoutService",
        type=ComponentType.SERVICE,
        domain="Checkout",
        location="server/polar/checkout/service.py",
        language="python",
        capabilities=[Capability(name="Customer lookup")],
        responsibilities=[Responsibility(name="Checkout lifecycle")],
        reads=["Customer", "Discount"],
        writes=["Checkout"],
        validates=["Customer exists", "Discount redeemable"],
        calls=["StripeService", "TaxService"],
        emits=["CheckoutConfirmed"],
        transactions=["Checkout transaction"],
        tests=["Checkout integration"],
    )

    assert component.id == "CheckoutService"
    assert component.type == ComponentType.SERVICE
    assert component.domain == "Checkout"
    assert len(component.capabilities) == 1
    assert len(component.responsibilities) == 1
    assert len(component.reads) == 2
    assert len(component.writes) == 1


def test_component_to_yaml():
    """Test YAML serialization of a component."""
    component = Component(
        id="CheckoutService",
        type=ComponentType.SERVICE,
        domain="Checkout",
        capabilities=[Capability(name="Customer lookup")],
        reads=["Customer"],
        writes=["Checkout"],
    )

    yaml = component.to_yaml()
    assert "Component:" in yaml
    assert "CheckoutService" in yaml
    assert "Customer lookup" in yaml
    assert "Customer" in yaml
    assert "Checkout" in yaml


def test_behavior_edge_creation():
    """Test that a BehaviorEdge can be created."""
    edge = BehaviorEdge(
        source_id="CheckoutService",
        target_id="Customer",
        edge_type=BehaviorEdgeType.READS,
    )

    assert edge.source_id == "CheckoutService"
    assert edge.target_id == "Customer"
    assert edge.edge_type == BehaviorEdgeType.READS


def test_behavior_graph_creation():
    """Test that a BehaviorGraph can be created."""
    component = Component(
        id="CheckoutService",
        type=ComponentType.SERVICE,
        domain="Checkout",
    )
    edge = BehaviorEdge(
        source_id="CheckoutService",
        target_id="Customer",
        edge_type=BehaviorEdgeType.READS,
    )
    domain = Domain(name="Checkout")

    graph = BehaviorGraph(
        components={"CheckoutService": component},
        edges=[edge],
        domains={"Checkout": domain},
    )

    assert graph.get_component("CheckoutService") == component
    assert len(graph.get_edges_from("CheckoutService")) == 1
    assert "Checkout" in graph.domains


def test_impact_result():
    """Test ImpactResult creation and serialization."""
    result = ImpactResult(
        changed_capability="Checkout confirmation",
        affected_components=["CheckoutService", "CustomerService"],
        affected_domains=["Checkout", "Customer"],
        affected_apis=["POST /checkout"],
        affected_tests=["test_checkout"],
    )

    assert result.changed_capability == "Checkout confirmation"
    assert len(result.affected_components) == 2
    assert "Checkout" in result.affected_domains

    yaml = result.to_yaml()
    assert "Checkout confirmation" in yaml
    assert "CheckoutService" in yaml


def test_change_delta():
    """Test ChangeDelta creation."""
    delta = ChangeDelta(
        delta_type=DeltaType.NEW_CAPABILITY,
        component_id="CheckoutService",
        description="New capability: Customer mutation",
        new_value="Customer mutation",
    )

    assert delta.delta_type == DeltaType.NEW_CAPABILITY
    assert delta.component_id == "CheckoutService"
    assert "Customer mutation" in delta.description


# ===== Tests for Agent 1: Component Builder =====


def test_component_builder_discovers_models():
    """Test that ComponentBuilder discovers model components."""
    graph = SemanticGraph()
    graph.add_node(_make_node(NodeType.MODEL, "Customer", "models/customer.py"))
    graph.add_node(_make_node(NodeType.MODEL, "Checkout", "models/checkout.py"))

    builder = ComponentBuilder()
    components = builder.build(graph)

    assert "Customer" in components
    assert components["Customer"].type == ComponentType.MODEL
    assert "Checkout" in components


def test_component_builder_discovers_services():
    """Test that ComponentBuilder discovers service components."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.CLASS, "CheckoutService", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "process_checkout", "services/checkout.py"
    ))

    builder = ComponentBuilder()
    components = builder.build(graph)

    assert "CheckoutService" in components
    assert components["CheckoutService"].type == ComponentType.SERVICE


def test_component_builder_discovers_apis():
    """Test that ComponentBuilder discovers API components."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.ENDPOINT, "checkout", "api/checkout.py",
        method="POST", route="/checkout"
    ))

    builder = ComponentBuilder()
    components = builder.build(graph)

    # API components use "METHOD /route" as ID
    api_ids = [k for k in components.keys() if "POST" in k or "checkout" in k]
    assert len(api_ids) > 0
    assert components[list(components.keys())[0]].type == ComponentType.API


def test_component_builder_discovers_jobs():
    """Test that ComponentBuilder discovers job components."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.FUNCTION, "send_email_job", "jobs/email.py"
    ))
    graph.add_node(_make_node(
        NodeType.CLASS, "ProcessWorker", "jobs/worker.py"
    ))

    builder = ComponentBuilder()
    components = builder.build(graph)

    assert "send_email_job" in components
    assert components["send_email_job"].type == ComponentType.JOB
    assert "ProcessWorker" in components


def test_component_builder_never_exposes_helpers():
    """Test that helper methods are not exposed as components."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.FUNCTION, "_get_validated_discount", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "_helper_util", "utils/helpers.py"
    ))

    builder = ComponentBuilder()
    components = builder.build(graph)

    # Private helpers should not be discovered as components
    for comp_id in components:
        assert not comp_id.startswith("_get_validated_"), \
            f"Helper method {comp_id} should not be a component"
        assert not comp_id.startswith("_helper_"), \
            f"Helper method {comp_id} should not be a component"


# ===== Tests for Agent 2: Repository Interpreter =====


def test_repository_interpreter_reads():
    """Test that repository read methods produce READ edges."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.FUNCTION, "get_customer", "repositories/customer_repo.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "find_by_email", "repositories/customer_repo.py"
    ))

    components = {
        "CustomerRepository": Component(
            id="CustomerRepository",
            type=ComponentType.REPOSITORY,
            domain="Customer",
            location="repositories/customer_repo.py",
        )
    }

    interpreter = RepositoryInterpreter()
    edges = interpreter.interpret(components, graph)

    read_edges = [e for e in edges if e.edge_type == BehaviorEdgeType.READS]
    assert len(read_edges) > 0


def test_repository_interpreter_writes():
    """Test that repository write methods produce WRITE edges."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.FUNCTION, "create_customer", "repositories/customer_repo.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "update_customer", "repositories/customer_repo.py"
    ))

    components = {
        "CustomerRepository": Component(
            id="CustomerRepository",
            type=ComponentType.REPOSITORY,
            domain="Customer",
            location="repositories/customer_repo.py",
        )
    }

    interpreter = RepositoryInterpreter()
    edges = interpreter.interpret(components, graph)

    write_edges = [e for e in edges if e.edge_type == BehaviorEdgeType.WRITES]
    assert len(write_edges) > 0


def test_repository_interpreter_ignores_orm_syntax():
    """Test that ORM syntax like where(), select() are ignored."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.FUNCTION, "where", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "select", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "execute", "services/checkout.py"
    ))

    components = {
        "CheckoutService": Component(
            id="CheckoutService",
            type=ComponentType.SERVICE,
            domain="Checkout",
        )
    }

    interpreter = RepositoryInterpreter()
    edges = interpreter.interpret(components, graph)

    # ORM syntax methods should not produce edges
    read_edges = [e for e in edges if e.edge_type == BehaviorEdgeType.READS]
    write_edges = [e for e in edges if e.edge_type == BehaviorEdgeType.WRITES]
    assert len(read_edges) + len(write_edges) == 0


# ===== Tests for Agent 3: Capability Extractor =====


def test_capability_extractor_from_validate():
    """Test that validate methods produce validation capabilities."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.FUNCTION, "validate_price", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "validate_discount", "services/checkout.py"
    ))

    components = {
        "CheckoutService": Component(
            id="CheckoutService",
            type=ComponentType.SERVICE,
            domain="Checkout",
            location="services/checkout.py",
        )
    }

    extractor = CapabilityExtractor()
    extractor.extract(components, graph)

    caps = [c.name for c in components["CheckoutService"].capabilities]
    assert "Price validation" in caps
    assert "Discount validation" in caps


def test_capability_extractor_from_lookup():
    """Test that get methods produce lookup capabilities."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.FUNCTION, "get_customer", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "get_subscription", "services/checkout.py"
    ))

    components = {
        "CheckoutService": Component(
            id="CheckoutService",
            type=ComponentType.SERVICE,
            domain="Checkout",
            location="services/checkout.py",
        )
    }

    extractor = CapabilityExtractor()
    extractor.extract(components, graph)

    caps = [c.name for c in components["CheckoutService"].capabilities]
    assert "Customer lookup" in caps
    assert "Subscription lookup" in caps


def test_capability_extractor_from_create():
    """Test that create methods produce capabilities."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.FUNCTION, "create_checkout", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "create_or_update_customer", "services/checkout.py"
    ))

    components = {
        "CheckoutService": Component(
            id="CheckoutService",
            type=ComponentType.SERVICE,
            domain="Checkout",
            location="services/checkout.py",
        )
    }

    extractor = CapabilityExtractor()
    extractor.extract(components, graph)

    caps = [c.name for c in components["CheckoutService"].capabilities]
    assert "Checkout creation" in caps
    assert "Customer mutation" in caps


def test_capability_extractor_from_confirm():
    """Test that confirm method produces confirmation capability."""
    graph = SemanticGraph()
    graph.add_node(_make_node(
        NodeType.FUNCTION, "confirm", "services/checkout.py"
    ))

    components = {
        "CheckoutService": Component(
            id="CheckoutService",
            type=ComponentType.SERVICE,
            domain="Checkout",
            location="services/checkout.py",
        )
    }

    extractor = CapabilityExtractor()
    extractor.extract(components, graph)

    caps = [c.name for c in components["CheckoutService"].capabilities]
    assert "Confirmation" in caps


# ===== Tests for Agent 4: Responsibility Builder =====


def test_responsibility_builder():
    """Test that responsibilities are built from capabilities and type."""
    component = Component(
        id="CheckoutService",
        type=ComponentType.SERVICE,
        domain="Checkout",
        capabilities=[Capability(name="Customer lookup"),
                      Capability(name="Checkout confirmation")],
    )

    builder = ResponsibilityBuilder()
    builder.build({"CheckoutService": component}, [])

    resp_names = [r.name for r in component.responsibilities]
    assert "CheckoutService lifecycle" in resp_names
    assert "Checkout confirmation" in resp_names


# ===== Tests for Agent 5: Dependency Builder =====


def test_dependency_builder_from_calls():
    """Test that CALLS edges create CALLS behavior edges."""
    graph = SemanticGraph()

    source = _make_node(
        NodeType.FUNCTION, "CheckoutService", "services/checkout.py"
    )
    target = _make_node(
        NodeType.FUNCTION, "PaymentService", "services/payment.py"
    )

    graph.add_node(source)
    graph.add_node(target)
    graph.add_edge(_make_edge(EdgeType.CALLS, source, target))

    components = {
        "CheckoutService": Component(
            id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        ),
        "PaymentService": Component(
            id="PaymentService", type=ComponentType.SERVICE, domain="Payment",
        ),
    }

    builder = DependencyBuilder()
    edges = builder.build(components, graph)

    calls_edges = [e for e in edges if e.edge_type == BehaviorEdgeType.CALLS]
    assert len(calls_edges) > 0


def test_dependency_builder_from_persistence():
    """Test that WRITES edges create WRITES behavior edges."""
    graph = SemanticGraph()

    source = _make_node(
        NodeType.FUNCTION, "CheckoutService", "services/checkout.py"
    )
    target = _make_node(
        NodeType.MODEL, "Checkout", "models/checkout.py"
    )

    graph.add_node(source)
    graph.add_node(target)
    graph.add_edge(_make_edge(EdgeType.WRITES, source, target))

    components = {
        "CheckoutService": Component(
            id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        ),
    }

    builder = DependencyBuilder()
    edges = builder.build(components, graph)

    write_edges = [e for e in edges if e.edge_type == BehaviorEdgeType.WRITES]
    assert len(write_edges) > 0


# ===== Tests for Agent 6: Domain Mapper =====


def test_domain_mapper_checkout():
    """Test that checkout-related names map to Checkout domain."""
    component = Component(
        id="CheckoutService",
        type=ComponentType.SERVICE,
        domain="",
    )

    mapper = DomainMapper()
    graph = SemanticGraph()
    graph.add_node(_make_node(NodeType.FUNCTION, "CheckoutService", "services/checkout.py"))

    domains = mapper.map({"CheckoutService": component}, graph)

    assert component.domain == "Checkout"
    assert "Checkout" in domains


def test_domain_mapper_customer():
    """Test that customer-related names map to Customer domain."""
    component = Component(
        id="CustomerRepository",
        type=ComponentType.REPOSITORY,
        domain="",
    )

    mapper = DomainMapper()
    graph = SemanticGraph()
    graph.add_node(_make_node(NodeType.FUNCTION, "CustomerRepository", "repos/customer.py"))

    domains = mapper.map({"CustomerRepository": component}, graph)

    assert component.domain == "Customer"


# ===== Tests for Agent 7: Change Analyzer =====


def test_change_analyzer_new_capability():
    """Test detection of new capabilities."""
    old_graph = BehaviorGraph()
    new_graph = BehaviorGraph()

    old_graph.components["CheckoutService"] = Component(
        id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        capabilities=[Capability(name="Customer lookup")],
    )
    new_graph.components["CheckoutService"] = Component(
        id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        capabilities=[Capability(name="Customer lookup"),
                      Capability(name="Price validation")],
    )

    analyzer = ChangeAnalyzer()
    deltas = analyzer.analyze(old_graph, new_graph)

    new_caps = [d for d in deltas if d.delta_type == DeltaType.NEW_CAPABILITY]
    assert len(new_caps) > 0
    assert any("Price validation" in d.description for d in new_caps)


def test_change_analyzer_removed_capability():
    """Test detection of removed capabilities."""
    old_graph = BehaviorGraph()
    new_graph = BehaviorGraph()

    old_graph.components["CheckoutService"] = Component(
        id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        capabilities=[Capability(name="Customer lookup"),
                      Capability(name="Price validation")],
    )
    new_graph.components["CheckoutService"] = Component(
        id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        capabilities=[Capability(name="Customer lookup")],
    )

    analyzer = ChangeAnalyzer()
    deltas = analyzer.analyze(old_graph, new_graph)

    removed_caps = [d for d in deltas if d.delta_type == DeltaType.REMOVED_CAPABILITY]
    assert len(removed_caps) > 0


def test_change_analyzer_validation_change():
    """Test detection of validation changes."""
    old_graph = BehaviorGraph()
    new_graph = BehaviorGraph()

    old_graph.components["CheckoutService"] = Component(
        id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        validates=["Customer exists"],
    )
    new_graph.components["CheckoutService"] = Component(
        id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        validates=["Customer exists", "Discount redeemable"],
    )

    analyzer = ChangeAnalyzer()
    deltas = analyzer.analyze(old_graph, new_graph)

    validation_deltas = [d for d in deltas if d.delta_type == DeltaType.MODIFIED_VALIDATION]
    assert len(validation_deltas) > 0


# ===== Tests for Agent 8: Stable Fact Filter =====


def test_stable_fact_filter_removes_framework_syntax():
    """Test that framework syntax is filtered out."""
    component = Component(
        id="CheckoutService",
        type=ComponentType.SERVICE,
        domain="Checkout",
        reads=["Customer", "session", "request", "select"],
        writes=["Checkout", "where", "execute"],
    )

    filter_ = StableFactFilter()
    filtered = filter_.filter_components({"CheckoutService": component})

    check = filtered["CheckoutService"]
    assert "Customer" in check.reads
    assert "session" not in check.reads
    assert "request" not in check.reads
    assert "select" not in check.reads
    assert "where" not in check.writes
    assert "execute" not in check.writes


def test_stable_fact_filter_keeps_stable_facts():
    """Test that stable facts are preserved."""
    component = Component(
        id="CheckoutService",
        type=ComponentType.SERVICE,
        domain="Checkout",
        reads=["Customer", "Discount"],
        writes=["Checkout", "DiscountRedemption"],
        validates=["Customer exists"],
        calls=["StripeService"],
        emits=["CheckoutConfirmed"],
    )

    filter_ = StableFactFilter()
    filtered = filter_.filter_components({"CheckoutService": component})

    check = filtered["CheckoutService"]
    assert "Customer" in check.reads
    assert "Checkout" in check.writes
    assert "Customer exists" in check.validates
    assert "StripeService" in check.calls
    assert "CheckoutConfirmed" in check.emits


# ===== Tests for Agent 9: Behavior Graph Builder =====


def test_graph_builder_assembles_graph():
    """Test that GraphBuilder assembles a complete BehaviorGraph."""
    components = {
        "CheckoutService": Component(
            id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
            capabilities=[Capability(name="Customer lookup")],
        ),
    }
    edges = [
        BehaviorEdge(
            source_id="CheckoutService", target_id="Customer",
            edge_type=BehaviorEdgeType.READS,
        ),
    ]
    domains = {"Checkout": Domain(name="Checkout")}

    builder = BehaviorGraphBuilder()
    graph = builder.build(components, edges, domains)

    assert "CheckoutService" in graph.components
    assert len(graph.edges) > 0
    assert "Checkout" in graph.domains


def test_graph_builder_enriches_components():
    """Test that components are enriched with edge-derived data."""
    components = {
        "CheckoutService": Component(
            id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        ),
    }
    edges = [
        BehaviorEdge(
            source_id="CheckoutService", target_id="Customer",
            edge_type=BehaviorEdgeType.READS,
        ),
        BehaviorEdge(
            source_id="CheckoutService", target_id="StripeService",
            edge_type=BehaviorEdgeType.CALLS,
        ),
    ]

    builder = BehaviorGraphBuilder()
    graph = builder.build(components, edges, {})

    checkout = graph.get_component("CheckoutService")
    assert "Customer" in checkout.reads
    assert "StripeService" in checkout.calls


# ===== Tests for Agent 10: Deterministic Impact Engine =====


def test_impact_engine_direct_impact():
    """Test that direct dependencies are found."""
    graph = BehaviorGraph()
    graph.components["CheckoutService"] = Component(
        id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        capabilities=[Capability(name="Customer lookup")],
    )
    graph.components["CustomerService"] = Component(
        id="CustomerService", type=ComponentType.SERVICE, domain="Customer",
    )

    deltas = [
        ChangeDelta(
            delta_type=DeltaType.MODIFIED_VALIDATION,
            component_id="CheckoutService",
            description="Modified validation",
        ),
    ]

    engine = DeterministicImpactEngine()
    results = engine.compute(deltas, graph)

    assert len(results) > 0


def test_impact_engine_finds_tests():
    """Test that tests are found from affected components."""
    graph = BehaviorGraph()
    graph.components["CheckoutService"] = Component(
        id="CheckoutService", type=ComponentType.SERVICE, domain="Checkout",
        tests=["test_checkout_integration"],
    )

    deltas = [
        ChangeDelta(
            delta_type=DeltaType.MODIFIED_VALIDATION,
            component_id="CheckoutService",
            description="Modified validation",
        ),
    ]

    engine = DeterministicImpactEngine()
    test_names = engine.find_tests_for_changes(deltas, graph)

    assert "test_checkout_integration" in test_names


# ===== Full Pipeline Tests =====


def test_full_pipeline_builds_components():
    """Test that the full pipeline builds components from a graph."""
    graph = SemanticGraph()

    # Models
    graph.add_node(_make_node(NodeType.MODEL, "Checkout", "models/checkout.py"))
    graph.add_node(_make_node(NodeType.MODEL, "Customer", "models/customer.py"))

    # Service
    graph.add_node(_make_node(
        NodeType.CLASS, "CheckoutService", "services/checkout.py"
    ))

    # Endpoint
    graph.add_node(_make_node(
        NodeType.ENDPOINT, "checkout", "api/checkout.py",
        method="POST", route="/checkout"
    ))

    # Functions
    graph.add_node(_make_node(
        NodeType.FUNCTION, "process_checkout", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "validate_price", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "get_customer", "services/checkout.py"
    ))

    # Edges
    nodes = list(graph.nodes.values())
    checkout_service = next(n for n in nodes if n.name == "CheckoutService")
    process = next(n for n in nodes if n.name == "process_checkout")
    validate = next(n for n in nodes if n.name == "validate_price")

    graph.add_edge(_make_edge(EdgeType.CALLS, checkout_service, process))
    graph.add_edge(_make_edge(EdgeType.CALLS, process, validate))

    pipeline = BehaviorGraphPipeline()
    result = pipeline.run(graph)

    # Should have components
    assert len(result.graph.components) > 0

    # CheckoutService should exist
    assert any(
        "CheckoutService" in c.id for c in result.graph.components.values()
    )


def test_full_pipeline_no_framework_syntax():
    """Test that the pipeline removes all framework syntax from output."""
    graph = SemanticGraph()

    graph.add_node(_make_node(
        NodeType.CLASS, "CheckoutService", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "session.execute", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "statement.where", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "joinedload", "services/checkout.py"
    ))

    pipeline = BehaviorGraphPipeline()
    result = pipeline.run(graph)

    # The output graph should not contain framework syntax
    for component in result.graph.components.values():
        for read in component.reads:
            assert read.lower() not in ("session.execute", "statement.where",
                                         "joinedload", "execute", "where"), \
                f"Framework syntax '{read}' leaked through"
        for write in component.writes:
            assert write.lower() not in ("session.execute", "statement.where",
                                          "joinedload"), \
                f"Framework syntax '{write}' leaked through"


def test_full_pipeline_impact_on_change():
    """Test that the pipeline computes impact when old graph is provided."""
    new_graph = SemanticGraph()

    new_graph.add_node(_make_node(
        NodeType.CLASS, "CheckoutService", "services/checkout.py"
    ))
    new_graph.add_node(_make_node(
        NodeType.FUNCTION, "validate_price", "services/checkout.py"
    ))
    new_graph.add_node(_make_node(
        NodeType.FUNCTION, "confirm", "services/checkout.py"
    ))

    old_graph = SemanticGraph()
    old_graph.add_node(_make_node(
        NodeType.CLASS, "CheckoutService", "services/checkout.py"
    ))
    old_graph.add_node(_make_node(
        NodeType.FUNCTION, "validate_price", "services/checkout.py"
    ))

    pipeline = BehaviorGraphPipeline()
    result = pipeline.run(new_graph, old_graph)

    # Should detect new capabilities (confirm was added)
    deltas = result.deltas
    assert len(deltas) > 0


def test_full_pipeline_yaml_output():
    """Test that the pipeline produces valid YAML-like output."""
    graph = SemanticGraph()

    graph.add_node(_make_node(
        NodeType.CLASS, "CheckoutService", "services/checkout.py"
    ))
    graph.add_node(_make_node(
        NodeType.FUNCTION, "validate_price", "services/checkout.py"
    ))

    pipeline = BehaviorGraphPipeline()
    result = pipeline.run(graph)

    yaml = result.to_yaml()
    assert "Behavior Graph Pipeline Result" in yaml
    assert "CheckoutService" in yaml


def test_full_pipeline_with_complex_workload():
    """Test the pipeline with a complex, realistic workload."""
    graph = SemanticGraph()

    # Add models
    graph.add_node(_make_node(NodeType.MODEL, "Checkout", "models.py",
                               change_type="added"))
    graph.add_node(_make_node(NodeType.MODEL, "DiscountRedemption", "models.py",
                               change_type="added"))
    graph.add_node(_make_node(NodeType.MODEL, "Customer", "models.py",
                               change_type="added"))

    # Add services
    graph.add_node(_make_node(NodeType.CLASS, "CheckoutService",
                               "services/checkout.py", change_type="added"))
    graph.add_node(_make_node(NodeType.CLASS, "DiscountService",
                               "services/discount.py", change_type="added"))

    # Add endpoints
    graph.add_node(_make_node(NodeType.ENDPOINT, "create_checkout",
                               "api/checkout.py", change_type="added",
                               method="POST", route="/checkout"))

    # Add functions
    graph.add_node(_make_node(NodeType.FUNCTION, "confirm",
                               "services/checkout.py", change_type="added"))
    graph.add_node(_make_node(NodeType.FUNCTION, "validate_discount",
                               "services/discount.py", change_type="added"))

    pipeline = BehaviorGraphPipeline()
    result = pipeline.run(graph)

    # Verify the results
    assert len(result.graph.components) > 0

    # Check for CheckoutService
    checkout_services = [c for c in result.graph.components.values()
                         if "Checkout" in c.id and c.type == ComponentType.SERVICE]
    assert len(checkout_services) > 0