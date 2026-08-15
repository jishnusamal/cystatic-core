import pytest
from engine.repository.facts import (
    FileId,
    SymbolId,
    EventId,
    EndpointId,
    ResourceId,
    File,
    Symbol,
    SymbolKind,
    SymbolVisibility,
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
from engine.repository.store import SQLiteRepositoryStore
from engine.repository.store.sink import PersistentFactSink


def test_round_trip_all_facts():
    """
    Verifies that every fact type can be written to the SQLite sink
    and read back correctly via SQLiteRepositoryStore.
    """
    store = SQLiteRepositoryStore(":memory:")
    repo_id = store.create_repository("github", "testowner", "testrepo")
    version_id = store.create_version(repo_id, "abc123commit")
    store.set_version_context(repo_id, version_id)
    
    sink = PersistentFactSink(store, repo_id, version_id)

    # 1. File
    file_fact = File(id=FileId(1), path="test.py", language="python")
    sink.add_file(file_fact)
    
    # 2. Symbol
    symbol_fact = Symbol(
        id=SymbolId(10),
        name="my_func",
        file_id=file_fact.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=5,
        end_line=15,
        visibility=SymbolVisibility.PUBLIC,
        parent_symbol_id=None
    )
    sink.add_symbol(symbol_fact)
    
    # 3. Call
    call_fact = Call(caller_id=SymbolId(10), callee_id=SymbolId(20), call_type=CallType.DIRECT)
    sink.add_call(call_fact)
    
    # 4. Reference
    ref_fact = Reference(source_id=SymbolId(10), target_id=SymbolId(30), relation_type=ReferenceType.REFERENCE)
    sink.add_reference(ref_fact)
    
    # 5. Import
    import_fact = Import(
        source_file_id=file_fact.id,
        target_file_id=FileId(2),
        module="os",
        imported_name="path",
        import_type=ImportType.STANDARD
    )
    sink.add_import(import_fact)
    
    # 6. TypeRelationship
    type_fact = TypeRelationship(source_id=SymbolId(10), target_id=SymbolId(40), relationship_type=TypeRelationshipType.INHERITS)
    sink.add_type_relationship(type_fact)
    
    # 7. Endpoint
    endpoint_fact = Endpoint(
        id=EndpointId(50),
        symbol_id=SymbolId(10),
        method=EndpointMethod.GET,
        path="/items",
        framework="FastAPI"
    )
    sink.add_endpoint(endpoint_fact)
    
    # 8. DatabaseRelationship
    db_fact = DatabaseRelationship(
        symbol_id=SymbolId(10),
        resource_id=ResourceId(99),
        relationship_type=DatabaseRelationshipType.READ
    )
    sink.add_database_relationship(db_fact)
    
    # 9. EventPublication
    pub_fact = EventPublication(
        symbol_id=SymbolId(10),
        event_id=EventId(88),
        publication_type=EventPublicationType.PUBLISH
    )
    sink.add_event_publication(pub_fact)
    
    # 10. EventSubscription
    sub_fact = EventSubscription(
        symbol_id=SymbolId(11),
        event_id=EventId(88),
        subscription_type=EventSubscriptionType.SUBSCRIBE
    )
    sink.add_event_subscription(sub_fact)
    
    # 11. TestRelationship
    test_fact = TestRelationship(
        test_symbol_id=SymbolId(999),
        target_symbol_id=SymbolId(10),
        relationship_type=TestRelationshipType.COVERS
    )
    sink.add_test_relationship(test_fact)
    
    sink.flush()

    # Query & Verify
    assert store.get_file(file_fact.id) == file_fact
    assert store.get_symbol(symbol_fact.id) == symbol_fact
    assert store.get_callees(SymbolId(10)) == (call_fact,)
    assert store.get_callers(SymbolId(20)) == (call_fact,)
    assert store.get_references_from(SymbolId(10)) == (ref_fact,)
    assert store.get_references_to(SymbolId(30)) == (ref_fact,)
    assert store.get_imports(file_fact.id) == (import_fact,)
    assert store.get_importers(FileId(2)) == (import_fact,)
    assert store.get_type_relationships(SymbolId(10)) == (type_fact,)
    assert store.get_type_dependents(SymbolId(40)) == (type_fact,)
    assert store.get_endpoints(SymbolId(10)) == (endpoint_fact,)
    assert store.get_database_relationships(SymbolId(10)) == (db_fact,)
    assert store.get_published_events(SymbolId(10)) == (pub_fact,)
    assert store.get_event_consumers(EventId(88)) == (sub_fact,)
    assert store.get_tests(SymbolId(10)) == (test_fact,)


def test_query_equivalence():
    """
    Run InMemoryRepository and SQLiteRepositoryStore against the same set of facts,
    verifying all query methods produce identical results.
    """
    # 1. Define synthetic facts
    file_main = File(id=FileId(1), path="app.py", language="python")
    file_lib = File(id=FileId(2), path="lib.py", language="python")
    
    symbol_a = Symbol(id=SymbolId(1), name="A", file_id=file_main.id, kind=SymbolKind.FUNCTION, language="python", start_line=1, end_line=10)
    symbol_b = Symbol(id=SymbolId(2), name="B", file_id=file_main.id, kind=SymbolKind.FUNCTION, language="python", start_line=11, end_line=20)
    symbol_c = Symbol(id=SymbolId(3), name="C", file_id=file_lib.id, kind=SymbolKind.FUNCTION, language="python", start_line=1, end_line=5)
    symbol_d = Symbol(id=SymbolId(4), name="ConsumerD", file_id=file_lib.id, kind=SymbolKind.FUNCTION, language="python", start_line=6, end_line=15)
    
    imp = Import(source_file_id=file_main.id, target_file_id=file_lib.id, module="lib", imported_name="C", import_type=ImportType.STANDARD)
    call_ab = Call(caller_id=symbol_a.id, callee_id=symbol_b.id, call_type=CallType.DIRECT)
    call_bc = Call(caller_id=symbol_b.id, callee_id=symbol_c.id, call_type=CallType.DIRECT)
    ref = Reference(source_id=symbol_a.id, target_id=symbol_b.id, relation_type=ReferenceType.REFERENCE)
    type_rel = TypeRelationship(source_id=symbol_b.id, target_id=symbol_c.id, relationship_type=TypeRelationshipType.INHERITS)
    endpoint = Endpoint(id=EndpointId(1), symbol_id=symbol_a.id, method=EndpointMethod.POST, path="/foo", framework="FastAPI")
    db_rel = DatabaseRelationship(symbol_id=symbol_b.id, resource_id=ResourceId(99), relationship_type=DatabaseRelationshipType.WRITE)
    pub = EventPublication(symbol_id=symbol_a.id, event_id=EventId(100), publication_type=EventPublicationType.PUBLISH)
    sub = EventSubscription(symbol_id=symbol_d.id, event_id=EventId(100), subscription_type=EventSubscriptionType.SUBSCRIBE)
    test_rel = TestRelationship(test_symbol_id=SymbolId(999), target_symbol_id=symbol_d.id, relationship_type=TestRelationshipType.COVERS)

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

    # 2. InMemory repository
    in_mem_repo = InMemoryRepository(facts)

    # 3. SQLite repository
    sqlite_store = SQLiteRepositoryStore(":memory:")
    repo_id = sqlite_store.create_repository("github", "owner", "repo")
    version_id = sqlite_store.create_version(repo_id, "commit1")
    sqlite_store.set_version_context(repo_id, version_id)
    
    sink = PersistentFactSink(sqlite_store, repo_id, version_id)
    for f in facts.files: sink.add_file(f)
    for s in facts.symbols: sink.add_symbol(s)
    for c in facts.calls: sink.add_call(c)
    for r in facts.references: sink.add_reference(r)
    for i in facts.imports: sink.add_import(i)
    for tr in facts.type_relationships: sink.add_type_relationship(tr)
    for ep in facts.endpoints: sink.add_endpoint(ep)
    for db in facts.database_relationships: sink.add_database_relationship(db)
    for pb in facts.event_publications: sink.add_event_publication(pb)
    for sb in facts.event_subscriptions: sink.add_event_subscription(sb)
    for t in facts.test_relationships: sink.add_test_relationship(t)
    sink.flush()

    # 4. Compare all queries
    for file_id in (FileId(1), FileId(2), FileId(99)):
        assert in_mem_repo.get_file(file_id) == sqlite_store.get_file(file_id)
        assert set(in_mem_repo.get_imports(file_id)) == set(sqlite_store.get_imports(file_id))
        assert set(in_mem_repo.get_importers(file_id)) == set(sqlite_store.get_importers(file_id))

    for sym_id in (SymbolId(1), SymbolId(2), SymbolId(3), SymbolId(4), SymbolId(99)):
        assert in_mem_repo.get_symbol(sym_id) == sqlite_store.get_symbol(sym_id)
        assert set(in_mem_repo.get_callers(sym_id)) == set(sqlite_store.get_callers(sym_id))
        assert set(in_mem_repo.get_callees(sym_id)) == set(sqlite_store.get_callees(sym_id))
        assert set(in_mem_repo.get_references_from(sym_id)) == set(sqlite_store.get_references_from(sym_id))
        assert set(in_mem_repo.get_references_to(sym_id)) == set(sqlite_store.get_references_to(sym_id))
        assert set(in_mem_repo.get_type_relationships(sym_id)) == set(sqlite_store.get_type_relationships(sym_id))
        assert set(in_mem_repo.get_type_dependents(sym_id)) == set(sqlite_store.get_type_dependents(sym_id))
        assert set(in_mem_repo.get_endpoints(sym_id)) == set(sqlite_store.get_endpoints(sym_id))
        assert set(in_mem_repo.get_database_relationships(sym_id)) == set(sqlite_store.get_database_relationships(sym_id))
        assert set(in_mem_repo.get_published_events(sym_id)) == set(sqlite_store.get_published_events(sym_id))
        assert set(in_mem_repo.get_tests(sym_id)) == set(sqlite_store.get_tests(sym_id))

    for ev_id in (EventId(100), EventId(999)):
        assert set(in_mem_repo.get_event_consumers(ev_id)) == set(sqlite_store.get_event_consumers(ev_id))


def test_repository_version_isolation():
    """
    Ensures that queries under Repository A's context never return
    Repository B's facts or different version facts.
    """
    store = SQLiteRepositoryStore(":memory:")
    
    repo_a = store.create_repository("github", "ownerA", "repoA")
    v_a = store.create_version(repo_a, "commitA")
    
    repo_b = store.create_repository("github", "ownerB", "repoB")
    v_b = store.create_version(repo_b, "commitB")

    # Add file & symbol to Repo A
    sink_a = PersistentFactSink(store, repo_a, v_a)
    sink_a.add_file(File(id=FileId(1), path="app.py", language="python"))
    sink_a.add_symbol(Symbol(id=SymbolId(1), name="funcA", file_id=FileId(1), kind=SymbolKind.FUNCTION, language="python", start_line=1, end_line=5))
    sink_a.flush()

    # Add file & symbol to Repo B
    sink_b = PersistentFactSink(store, repo_b, v_b)
    sink_b.add_file(File(id=FileId(1), path="lib.py", language="python"))
    sink_b.add_symbol(Symbol(id=SymbolId(1), name="funcB", file_id=FileId(1), kind=SymbolKind.FUNCTION, language="python", start_line=1, end_line=5))
    sink_b.flush()

    # Query under Repo A context
    store.set_version_context(repo_a, v_a)
    file_res = store.get_file(FileId(1))
    assert file_res is not None
    assert file_res.path == "app.py"
    
    sym_res = store.get_symbol(SymbolId(1))
    assert sym_res is not None
    assert sym_res.name == "funcA"

    # Query under Repo B context
    store.set_version_context(repo_b, v_b)
    file_res = store.get_file(FileId(1))
    assert file_res is not None
    assert file_res.path == "lib.py"
    
    sym_res = store.get_symbol(SymbolId(1))
    assert sym_res is not None
    assert sym_res.name == "funcB"
