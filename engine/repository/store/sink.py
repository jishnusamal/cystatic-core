from engine.repository.indexing.sink import RepositoryFactSink
from engine.repository.facts import (
    File,
    FileId,
    Symbol,
    SymbolId,
    Call,
    Reference,
    Import,
    TypeRelationship,
    Endpoint,
    DatabaseRelationship,
    EventPublication,
    EventSubscription,
    TestRelationship,
)
from .sqlite import SQLiteRepositoryStore


class PersistentFactSink(RepositoryFactSink):
    """
    Writes extracted facts directly to the SQLite repository store.
    
    Uses transactions to batch updates for performance without accumulating
    records in memory.
    """

    def __init__(self, store: SQLiteRepositoryStore, repository_id: str, version_id: str) -> None:
        self.store = store
        self.repository_id = repository_id
        self.version_id = version_id
        self.conn = store.conn
        self._in_transaction = False

    def begin(self) -> None:
        """Starts a new SQLite transaction if not already in one."""
        if not self._in_transaction:
            self.conn.execute("BEGIN TRANSACTION;")
            self._in_transaction = True

    def flush(self) -> None:
        """Commits the current SQLite transaction."""
        if self._in_transaction:
            self.conn.commit()
            self._in_transaction = False

    def rollback(self) -> None:
        """Rolls back the current SQLite transaction in case of error."""
        if self._in_transaction:
            self.conn.rollback()
            self._in_transaction = False

    def add_file(self, file: File) -> FileId:
        self.begin()
        self.conn.execute(
            "INSERT OR REPLACE INTO files (repository_id, version_id, id, path, language) VALUES (?, ?, ?, ?, ?)",
            (self.repository_id, self.version_id, int(file.id), file.path, file.language)
        )
        return file.id

    def add_symbol(self, symbol: Symbol) -> SymbolId:
        self.begin()
        parent_id = int(symbol.parent_symbol_id) if symbol.parent_symbol_id is not None else None
        self.conn.execute(
            "INSERT OR REPLACE INTO symbols (repository_id, version_id, id, name, file_id, kind, language, start_line, end_line, visibility, parent_symbol_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self.repository_id,
                self.version_id,
                int(symbol.id),
                symbol.name,
                int(symbol.file_id),
                symbol.kind.value,
                symbol.language,
                symbol.start_line,
                symbol.end_line,
                symbol.visibility.value,
                parent_id,
            )
        )
        return symbol.id

    def add_call(self, call: Call) -> None:
        self.begin()
        self.conn.execute(
            "INSERT INTO calls (repository_id, version_id, caller_id, callee_id, call_type) VALUES (?, ?, ?, ?, ?)",
            (self.repository_id, self.version_id, int(call.caller_id), int(call.callee_id), call.call_type.value)
        )

    def add_reference(self, reference: Reference) -> None:
        self.begin()
        self.conn.execute(
            "INSERT INTO \"references\" (repository_id, version_id, source_id, target_id, relation_type) VALUES (?, ?, ?, ?, ?)",
            (self.repository_id, self.version_id, int(reference.source_id), int(reference.target_id), reference.relation_type.value)
        )

    def add_import(self, import_fact: Import) -> None:
        self.begin()
        target_file_id = int(import_fact.target_file_id) if import_fact.target_file_id is not None else None
        self.conn.execute(
            "INSERT INTO imports (repository_id, version_id, source_file_id, target_file_id, module, imported_name, import_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.repository_id,
                self.version_id,
                int(import_fact.source_file_id),
                target_file_id,
                import_fact.module,
                import_fact.imported_name,
                import_fact.import_type.value,
            )
        )

    def add_type_relationship(self, type_rel: TypeRelationship) -> None:
        self.begin()
        self.conn.execute(
            "INSERT INTO type_relationships (repository_id, version_id, source_id, target_id, relationship_type) VALUES (?, ?, ?, ?, ?)",
            (self.repository_id, self.version_id, int(type_rel.source_id), int(type_rel.target_id), type_rel.relationship_type.value)
        )

    def add_endpoint(self, endpoint: Endpoint) -> None:
        self.begin()
        self.conn.execute(
            "INSERT OR REPLACE INTO endpoints (repository_id, version_id, id, symbol_id, method, path, framework) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.repository_id,
                self.version_id,
                int(endpoint.id),
                int(endpoint.symbol_id),
                endpoint.method.value,
                endpoint.path,
                endpoint.framework,
            )
        )

    def add_database_relationship(self, db_rel: DatabaseRelationship) -> None:
        self.begin()
        self.conn.execute(
            "INSERT INTO database_relationships (repository_id, version_id, symbol_id, resource_id, relationship_type) VALUES (?, ?, ?, ?, ?)",
            (self.repository_id, self.version_id, int(db_rel.symbol_id), int(db_rel.resource_id), db_rel.relationship_type.value)
        )

    def add_event_publication(self, pub: EventPublication) -> None:
        self.begin()
        self.conn.execute(
            "INSERT INTO event_publications (repository_id, version_id, symbol_id, event_id, publication_type) VALUES (?, ?, ?, ?, ?)",
            (self.repository_id, self.version_id, int(pub.symbol_id), int(pub.event_id), pub.publication_type.value)
        )

    def add_event_subscription(self, sub: EventSubscription) -> None:
        self.begin()
        self.conn.execute(
            "INSERT INTO event_subscriptions (repository_id, version_id, symbol_id, event_id, subscription_type) VALUES (?, ?, ?, ?, ?)",
            (self.repository_id, self.version_id, int(sub.symbol_id), int(sub.event_id), sub.subscription_type.value)
        )

    def add_test_relationship(self, test_rel: TestRelationship) -> None:
        self.begin()
        self.conn.execute(
            "INSERT INTO test_relationships (repository_id, version_id, test_symbol_id, target_symbol_id, relationship_type) VALUES (?, ?, ?, ?, ?)",
            (self.repository_id, self.version_id, int(test_rel.test_symbol_id), int(test_rel.target_symbol_id), test_rel.relationship_type.value)
        )
