from engine.repository.facts import (
    FileId,
    SymbolId,
    EventId,
    EndpointId,
    ResourceId,
    File,
    Symbol,
    SymbolKind,
    Call,
    CallType,
    Import,
    ImportType,
    Reference,
    ReferenceType,
    TypeRelationship,
    TypeRelationshipType,
    Endpoint,
    EndpointMethod,
    DatabaseRelationship,
    DatabaseRelationshipType,
    EventPublication,
    EventPublicationType,
    EventSubscription,
    EventSubscriptionType,
    TestRelationship,
    TestRelationshipType,
    RepositoryFacts,
)
from engine.repository.query import InMemoryRepository


def test_golden_queries_synthetic_repository():
    """
    Builds the synthetic repository requested in Phase 2.7:
    
    A (Symbol 1)
      - calls -> B (Symbol 2) -> calls -> C (Symbol 3)
      - publishes -> EventX (EventId 100)
      - exposes -> POST /foo
      
    EventX (EventId 100)
      - subscribed by/consumed by -> ConsumerD (Symbol 4)
    """
    # 1. Define source files
    file_main = File(id=FileId(1), path="app.py", language="python")
    file_lib = File(id=FileId(2), path="lib.py", language="python")
    
    # 2. Define symbols
    symbol_a = Symbol(
        id=SymbolId(1),
        name="A",
        file_id=file_main.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=10,
    )
    symbol_b = Symbol(
        id=SymbolId(2),
        name="B",
        file_id=file_main.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=11,
        end_line=20,
    )
    symbol_c = Symbol(
        id=SymbolId(3),
        name="C",
        file_id=file_lib.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=5,
    )
    symbol_d = Symbol(
        id=SymbolId(4),
        name="ConsumerD",
        file_id=file_lib.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=6,
        end_line=15,
    )
    
    # 3. Define relationships
    # Import: app.py imports lib.py
    imp = Import(
        source_file_id=file_main.id,
        target_file_id=file_lib.id,
        module="lib",
        imported_name="C",
        import_type=ImportType.STANDARD,
    )

    # Calls: A -> B, B -> C
    call_ab = Call(caller_id=symbol_a.id, callee_id=symbol_b.id, call_type=CallType.DIRECT)
    call_bc = Call(caller_id=symbol_b.id, callee_id=symbol_c.id, call_type=CallType.DIRECT)

    # Reference: A references B (e.g. name reference)
    ref = Reference(source_id=symbol_a.id, target_id=symbol_b.id, relation_type=ReferenceType.REFERENCE)

    # Type relationship: B inherits from C (representing classes in this context)
    type_rel = TypeRelationship(source_id=symbol_b.id, target_id=symbol_c.id, relationship_type=TypeRelationshipType.INHERITS)

    # Endpoint: A exposes POST /foo
    endpoint = Endpoint(
        id=EndpointId(1),
        symbol_id=symbol_a.id,
        method=EndpointMethod.POST,
        path="/foo",
        framework="FastAPI",
    )

    # Database: B writes to Payments DB (ResourceId 99)
    db_rel = DatabaseRelationship(
        symbol_id=symbol_b.id,
        resource_id=ResourceId(99),
        relationship_type=DatabaseRelationshipType.WRITE,
    )

    # Event Pub: A publishes EventX (EventId 100)
    pub = EventPublication(
        symbol_id=symbol_a.id,
        event_id=EventId(100),
        publication_type=EventPublicationType.PUBLISH,
    )

    # Event Sub: ConsumerD (Symbol 4) consumes EventX (EventId 100)
    sub = EventSubscription(
        symbol_id=symbol_d.id,
        event_id=EventId(100),
        subscription_type=EventSubscriptionType.SUBSCRIBE,
    )

    # Test Relationship: ConsumerD is targeted by a test
    test_rel = TestRelationship(
        test_symbol_id=SymbolId(999),
        target_symbol_id=symbol_d.id,
        relationship_type=TestRelationshipType.COVERS,
    )

    # 4. Construct RepositoryFacts and InMemoryRepository
    facts = RepositoryFacts(
        files=(file_main, file_lib),
        symbols=(symbol_a, symbol_b, symbol_c, symbol_d),
        calls=(call_ab, call_bc),
        references=(ref,),
        imports=(imp,),
        type_relationships=(type_rel,),
        endpoints=(endpoint,),
        database_relationships=(db_rel,),
        event_publications=(pub,),
        event_subscriptions=(sub,),
        test_relationships=(test_rel,),
    )
    repo = InMemoryRepository(facts)

    # 5. Assert golden queries
    assert repo.get_symbol(symbol_a.id) == symbol_a
    assert repo.get_file(file_main.id) == file_main
    
    assert repo.get_callees(symbol_a.id) == (call_ab,)
    assert repo.get_callers(symbol_b.id) == (call_ab,)
    assert repo.get_callees(symbol_b.id) == (call_bc,)
    assert repo.get_callers(symbol_c.id) == (call_bc,)

    assert repo.get_published_events(symbol_a.id) == (pub,)
    assert repo.get_event_consumers(EventId(100)) == (sub,)
    assert repo.get_endpoints(symbol_a.id) == (endpoint,)
    
    assert repo.get_imports(file_main.id) == (imp,)
    assert repo.get_importers(file_lib.id) == (imp,)
    
    assert repo.get_references_from(symbol_a.id) == (ref,)
    assert repo.get_references_to(symbol_b.id) == (ref,)

    assert repo.get_type_relationships(symbol_b.id) == (type_rel,)
    assert repo.get_type_dependents(symbol_c.id) == (type_rel,)

    assert repo.get_database_relationships(symbol_b.id) == (db_rel,)
    assert repo.get_tests(symbol_d.id) == (test_rel,)
