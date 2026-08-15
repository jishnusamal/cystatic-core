import pytest
from engine.repository.facts import (
    File,
    FileId,
    Symbol,
    SymbolId,
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
    EndpointId,
    EndpointMethod,
    DatabaseRelationship,
    DatabaseRelationshipType,
    ResourceId,
    EventPublication,
    EventPublicationType,
    EventSubscription,
    EventSubscriptionType,
    EventId,
    TestRelationship,
    TestRelationshipType,
    RepositoryFacts,
)
from engine.repository.query import InMemoryRepository
from engine.repository.overlay import RepositoryOverlay, RepositoryView


def test_overlay_view_query_delegation():
    # 1. Setup Base Repository Facts
    base_file_a = File(id=FileId(1), path="a.py", language="python")
    base_file_b = File(id=FileId(2), path="b.py", language="python")

    base_sym_a = Symbol(
        id=SymbolId(10),
        name="funcA",
        file_id=FileId(1),
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=5,
    )
    base_sym_b = Symbol(
        id=SymbolId(20),
        name="funcB",
        file_id=FileId(2),
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=5,
    )

    base_call = Call(
        caller_id=SymbolId(20), callee_id=SymbolId(10), call_type=CallType.DIRECT
    )
    base_ref = Reference(
        source_id=SymbolId(20),
        target_id=SymbolId(10),
        relation_type=ReferenceType.REFERENCE,
    )
    base_imp = Import(
        source_file_id=FileId(2),
        target_file_id=FileId(1),
        module="a",
        imported_name="funcA",
        import_type=ImportType.FROM,
    )
    base_tr = TypeRelationship(
        source_id=SymbolId(20),
        target_id=SymbolId(10),
        relationship_type=TypeRelationshipType.EXTENDS,
    )
    base_ep = Endpoint(
        id=EndpointId(100),
        symbol_id=SymbolId(10),
        method=EndpointMethod.GET,
        path="/api",
        framework="django",
    )
    base_db = DatabaseRelationship(
        symbol_id=SymbolId(10),
        resource_id=ResourceId(1),
        relationship_type=DatabaseRelationshipType.READ,
    )
    base_pub = EventPublication(
        symbol_id=SymbolId(10),
        event_id=EventId(500),
        publication_type=EventPublicationType.PUBLISH,
    )
    base_sub = EventSubscription(
        symbol_id=SymbolId(20),
        event_id=EventId(500),
        subscription_type=EventSubscriptionType.SUBSCRIBE,
    )
    base_test = TestRelationship(
        test_symbol_id=SymbolId(20),
        target_symbol_id=SymbolId(10),
        relationship_type=TestRelationshipType.COVERS,
    )

    base_facts = RepositoryFacts(
        files=(base_file_a, base_file_b),
        symbols=(base_sym_a, base_sym_b),
        calls=(base_call,),
        references=(base_ref,),
        imports=(base_imp,),
        type_relationships=(base_tr,),
        endpoints=(base_ep,),
        database_relationships=(base_db,),
        event_publications=(base_pub,),
        event_subscriptions=(base_sub,),
        test_relationships=(base_test,),
    )
    base_query = InMemoryRepository(base_facts)

    # 2. Setup Overlay where:
    # - File B is modified (treated as removed in base, added in overlay)
    # - Call is removed
    # - New symbol added to File A
    overlay = RepositoryOverlay(
        removed_files={FileId(2)},
        modified_files={FileId(2)},
        added_files={
            FileId(2): base_file_b,
            FileId(3): File(id=FileId(3), path="c.py", language="python"),
        },
        removed_symbols={SymbolId(20)},
        added_symbols={
            SymbolId(20): Symbol(
                id=SymbolId(20),
                name="funcB_modified",
                file_id=FileId(2),
                kind=SymbolKind.FUNCTION,
                language="python",
                start_line=1,
                end_line=10,
            ),
            SymbolId(30): Symbol(
                id=SymbolId(30),
                name="funcC",
                file_id=FileId(3),
                kind=SymbolKind.FUNCTION,
                language="python",
                start_line=1,
                end_line=5,
            ),
        },
        removed_calls={base_call},
        added_calls={
            Call(
                caller_id=SymbolId(30),
                callee_id=SymbolId(10),
                call_type=CallType.DIRECT,
            )
        },
    )

    # 3. Create View
    view = RepositoryView(base_query, overlay)

    # 4. Verify View queries
    # File A and its symbol should be intact
    assert view.get_file(FileId(1)) == base_file_a
    assert view.get_symbol(SymbolId(10)) == base_sym_a

    # File B should be overridden
    assert view.get_file(FileId(2)) == base_file_b
    assert view.get_symbol(SymbolId(20)) == Symbol(
        id=SymbolId(20),
        name="funcB_modified",
        file_id=FileId(2),
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=10,
    )

    # File C should be added
    assert view.get_file(FileId(3)) == File(
        id=FileId(3), path="c.py", language="python"
    )
    assert view.get_symbol(SymbolId(30)) == Symbol(
        id=SymbolId(30),
        name="funcC",
        file_id=FileId(3),
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=5,
    )

    # Base call Ba should be removed, but new call Ca should be added
    assert view.get_callees(SymbolId(20)) == ()
    assert view.get_callers(SymbolId(10)) == (
        Call(caller_id=SymbolId(30), callee_id=SymbolId(10), call_type=CallType.DIRECT),
    )
    assert view.get_callees(SymbolId(30)) == (
        Call(caller_id=SymbolId(30), callee_id=SymbolId(10), call_type=CallType.DIRECT),
    )

    # Imports/references from modified File B should not leak from base
    assert view.get_imports(FileId(2)) == ()
    assert view.get_references_from(SymbolId(20)) == ()
    assert view.get_references_to(SymbolId(10)) == ()
