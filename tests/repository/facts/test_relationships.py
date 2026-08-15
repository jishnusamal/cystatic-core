from engine.repository.facts import (
    FileId,
    SymbolId,
    EventId,
    ResourceId,
    EndpointId,
    File,
    Symbol,
    SymbolKind,
    SymbolVisibility,
    Call,
    CallType,
    Reference,
    ReferenceType,
    Import,
    ImportType,
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


def test_repository_facts_lookup_apis():
    """
    Test setting up a tiny repository semantic graph using flat facts,
    and assert we can query it using RepositoryFacts APIs with zero nested objects.
    """
    # 1. Define files
    file_a = File(id=FileId(1), path="service.py", language="python")
    file_b = File(id=FileId(2), path="handler.py", language="python")
    file_t = File(id=FileId(3), path="test_service.py", language="python")

    # 2. Define symbols
    # A class in service.py
    symbol_class_a = Symbol(
        id=SymbolId(10),
        name="PaymentService",
        file_id=file_a.id,
        kind=SymbolKind.CLASS,
        language="python",
        start_line=1,
        end_line=20,
    )
    # A method inside class A
    symbol_method_a = Symbol(
        id=SymbolId(11),
        name="process",
        file_id=file_a.id,
        kind=SymbolKind.METHOD,
        language="python",
        start_line=5,
        end_line=15,
        parent_symbol_id=symbol_class_a.id,
    )
    # A handler function in handler.py
    symbol_handler_b = Symbol(
        id=SymbolId(20),
        name="CheckoutHandler",
        file_id=file_b.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=5,
        end_line=10,
    )
    # A test function in test_service.py
    symbol_test_t = Symbol(
        id=SymbolId(30),
        name="test_checkout_confirmation",
        file_id=file_t.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=5,
    )

    # 3. Define relationships
    # Import: handler.py imports service.py
    imp = Import(
        source_file_id=file_b.id,
        target_file_id=file_a.id,
        module="service",
        imported_name="PaymentService",
        import_type=ImportType.FROM,
    )

    # Call: CheckoutHandler calls PaymentService.process
    call = Call(
        caller_id=symbol_handler_b.id,
        callee_id=symbol_method_a.id,
        call_type=CallType.METHOD,
    )

    # Reference: PaymentService.process references some external helper/constant or class
    ref = Reference(
        source_id=symbol_method_a.id,
        target_id=symbol_class_a.id,
        relation_type=ReferenceType.REFERENCE,
    )

    # Type relationship: PaymentService extends BaseService (let's assume BaseService is Symbol 99)
    tr = TypeRelationship(
        source_id=symbol_class_a.id,
        target_id=SymbolId(99),
        relationship_type=TypeRelationshipType.EXTENDS,
    )

    # Endpoint: CheckoutHandler exposes POST /checkout/confirm
    endpoint = Endpoint(
        id=EndpointId(1),
        symbol_id=symbol_handler_b.id,
        method=EndpointMethod.POST,
        path="/checkout/confirm",
        framework="FastAPI",
    )

    # Database: PaymentService.process writes to 'payments' table
    db_rel = DatabaseRelationship(
        symbol_id=symbol_method_a.id,
        resource_id=ResourceId(501),
        relationship_type=DatabaseRelationshipType.WRITE,
    )

    # Event Pub: PaymentService.process publishes 'PaymentCompleted' event (EventId 1001)
    pub = EventPublication(
        symbol_id=symbol_method_a.id,
        event_id=EventId(1001),
        publication_type=EventPublicationType.PUBLISH,
    )

    # Event Sub: CheckoutHandler subscribes to 'PaymentCompleted'
    sub = EventSubscription(
        symbol_id=symbol_handler_b.id,
        event_id=EventId(1001),
        subscription_type=EventSubscriptionType.SUBSCRIBE,
    )

    # Test relationship: test_checkout_confirmation covers CheckoutHandler
    test_rel = TestRelationship(
        test_symbol_id=symbol_test_t.id,
        target_symbol_id=symbol_handler_b.id,
        relationship_type=TestRelationshipType.COVERS,
    )

    # Assemble RepositoryFacts
    facts = RepositoryFacts(
        files=(file_a, file_b, file_t),
        symbols=(symbol_class_a, symbol_method_a, symbol_handler_b, symbol_test_t),
        calls=(call,),
        references=(ref,),
        imports=(imp,),
        type_relationships=(tr,),
        endpoints=(endpoint,),
        database_relationships=(db_rel,),
        event_publications=(pub,),
        event_subscriptions=(sub,),
        test_relationships=(test_rel,),
    )

    # Assert get APIs
    assert facts.get_file(file_a.id) == file_a
    assert facts.get_symbol(symbol_method_a.id) == symbol_method_a

    # Assert relationship queries
    assert facts.calls_from(symbol_handler_b.id) == (call,)
    assert facts.calls_to(symbol_method_a.id) == (call,)

    assert facts.references_from(symbol_method_a.id) == (ref,)
    assert facts.references_to(symbol_class_a.id) == (ref,)

    assert facts.imports_from(file_b.id) == (imp,)

    assert facts.type_relationships_from(symbol_class_a.id) == (tr,)

    assert facts.endpoints_for(symbol_handler_b.id) == (endpoint,)

    assert facts.database_relationships_for(symbol_method_a.id) == (db_rel,)

    assert facts.publications_for(symbol_method_a.id) == (pub,)

    assert facts.subscriptions_for(EventId(1001)) == (sub,)

    assert facts.tests_for(symbol_handler_b.id) == (test_rel,)
