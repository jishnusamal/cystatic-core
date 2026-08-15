import sqlite3
import datetime
from typing import Any
from engine.repository.facts import (
    Call,
    CallType,
    DatabaseRelationship,
    DatabaseRelationshipType,
    Endpoint,
    EndpointId,
    EndpointMethod,
    EventId,
    EventPublication,
    EventPublicationType,
    EventSubscription,
    EventSubscriptionType,
    File,
    FileId,
    Import,
    ImportType,
    Reference,
    ReferenceType,
    ResourceId,
    Symbol,
    SymbolId,
    SymbolKind,
    SymbolVisibility,
    TestRelationship,
    TestRelationshipType,
    TypeRelationship,
    TypeRelationshipType,
)
from .store import RepositoryStore
from .schema import CREATE_TABLES_SQL, CREATE_INDEXES_SQL
from .errors import RepositoryNotFoundError, VersionNotFoundError


class SQLiteRepositoryStore(RepositoryStore):
    """
    SQLite-backed persistent implementation of RepositoryStore.
    
    Scopes all reads and writes to the set version context (repository_id, version_id).
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Enable WAL journal mode and foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")
        
        # Initialize schema
        with self.conn:
            self.conn.executescript(CREATE_TABLES_SQL)
            self.conn.executescript(CREATE_INDEXES_SQL)
            
        self.repository_id: str | None = None
        self.version_id: str | None = None

    def create_repository(self, provider: str, owner: str, name: str) -> str:
        repo_id = f"{provider}/{owner}/{name}"
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO repositories (id, provider, owner, name) VALUES (?, ?, ?, ?)",
                (repo_id, provider, owner, name)
            )
        return repo_id

    def create_version(self, repository_id: str, commit_sha: str) -> str:
        version_id = f"{repository_id}@{commit_sha}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO repository_versions (id, repository_id, commit_sha, created_at, status) VALUES (?, ?, ?, ?, ?)",
                (version_id, repository_id, commit_sha, created_at, "pending")
            )
        return version_id

    def set_version_context(self, repository_id: str, version_id: str) -> None:
        # Verify existence
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM repositories WHERE id = ?", (repository_id,))
        if not cur.fetchone():
            raise RepositoryNotFoundError(f"Repository {repository_id} not found.")
            
        cur.execute("SELECT 1 FROM repository_versions WHERE id = ?", (version_id,))
        if not cur.fetchone():
            raise VersionNotFoundError(f"Version {version_id} not found.")
            
        self.repository_id = repository_id
        self.version_id = version_id

    def _get_context(self) -> tuple[str, str]:
        if self.repository_id is None or self.version_id is None:
            raise RuntimeError("Repository and version context must be set before executing queries.")
        return self.repository_id, self.version_id

    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, file_id, kind, language, start_line, end_line, visibility, parent_symbol_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        row = cur.fetchone()
        if not row:
            return None
        return Symbol(
            id=SymbolId(row["id"]),
            name=row["name"],
            file_id=FileId(row["file_id"]),
            kind=SymbolKind(row["kind"]),
            language=row["language"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            visibility=SymbolVisibility(row["visibility"]),
            parent_symbol_id=SymbolId(row["parent_symbol_id"]) if row["parent_symbol_id"] is not None else None
        )

    def get_file(self, file_id: FileId) -> File | None:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, path, language FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, version_id, int(file_id))
        )
        row = cur.fetchone()
        if not row:
            return None
        return File(
            id=FileId(row["id"]),
            path=row["path"],
            language=row["language"]
        )

    def get_callers(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT caller_id, callee_id, call_type FROM calls WHERE repository_id = ? AND version_id = ? AND callee_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            Call(
                caller_id=SymbolId(row["caller_id"]),
                callee_id=SymbolId(row["callee_id"]),
                call_type=CallType(row["call_type"])
            )
            for row in cur.fetchall()
        )

    def get_callees(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT caller_id, callee_id, call_type FROM calls WHERE repository_id = ? AND version_id = ? AND caller_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            Call(
                caller_id=SymbolId(row["caller_id"]),
                callee_id=SymbolId(row["callee_id"]),
                call_type=CallType(row["call_type"])
            )
            for row in cur.fetchall()
        )

    def get_references_from(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_id, target_id, relation_type FROM \"references\" WHERE repository_id = ? AND version_id = ? AND source_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            Reference(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relation_type=ReferenceType(row["relation_type"])
            )
            for row in cur.fetchall()
        )

    def get_references_to(self, symbol_id: SymbolId) -> tuple[Reference, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_id, target_id, relation_type FROM \"references\" WHERE repository_id = ? AND version_id = ? AND target_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            Reference(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relation_type=ReferenceType(row["relation_type"])
            )
            for row in cur.fetchall()
        )

    def get_imports(self, file_id: FileId) -> tuple[Import, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_file_id, target_file_id, module, imported_name, import_type FROM imports WHERE repository_id = ? AND version_id = ? AND source_file_id = ?",
            (repo_id, version_id, int(file_id))
        )
        return tuple(
            Import(
                source_file_id=FileId(row["source_file_id"]),
                target_file_id=FileId(row["target_file_id"]) if row["target_file_id"] is not None else None,
                module=row["module"],
                imported_name=row["imported_name"],
                import_type=ImportType(row["import_type"])
            )
            for row in cur.fetchall()
        )

    def get_importers(self, file_id: FileId) -> tuple[Import, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_file_id, target_file_id, module, imported_name, import_type FROM imports WHERE repository_id = ? AND version_id = ? AND target_file_id = ?",
            (repo_id, version_id, int(file_id))
        )
        return tuple(
            Import(
                source_file_id=FileId(row["source_file_id"]),
                target_file_id=FileId(row["target_file_id"]) if row["target_file_id"] is not None else None,
                module=row["module"],
                imported_name=row["imported_name"],
                import_type=ImportType(row["import_type"])
            )
            for row in cur.fetchall()
        )

    def get_type_relationships(self, symbol_id: SymbolId) -> tuple[TypeRelationship, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_id, target_id, relationship_type FROM type_relationships WHERE repository_id = ? AND version_id = ? AND source_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            TypeRelationship(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relationship_type=TypeRelationshipType(row["relationship_type"])
            )
            for row in cur.fetchall()
        )

    def get_type_dependents(self, symbol_id: SymbolId) -> tuple[TypeRelationship, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_id, target_id, relationship_type FROM type_relationships WHERE repository_id = ? AND version_id = ? AND target_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            TypeRelationship(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relationship_type=TypeRelationshipType(row["relationship_type"])
            )
            for row in cur.fetchall()
        )

    def get_endpoints(self, symbol_id: SymbolId) -> tuple[Endpoint, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, symbol_id, method, path, framework FROM endpoints WHERE repository_id = ? AND version_id = ? AND symbol_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            Endpoint(
                id=EndpointId(row["id"]),
                symbol_id=SymbolId(row["symbol_id"]),
                method=EndpointMethod(row["method"]),
                path=row["path"],
                framework=row["framework"]
            )
            for row in cur.fetchall()
        )

    def get_database_relationships(self, symbol_id: SymbolId) -> tuple[DatabaseRelationship, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT symbol_id, resource_id, relationship_type FROM database_relationships WHERE repository_id = ? AND version_id = ? AND symbol_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            DatabaseRelationship(
                symbol_id=SymbolId(row["symbol_id"]),
                resource_id=ResourceId(row["resource_id"]),
                relationship_type=DatabaseRelationshipType(row["relationship_type"])
            )
            for row in cur.fetchall()
        )

    def get_published_events(self, symbol_id: SymbolId) -> tuple[EventPublication, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT symbol_id, event_id, publication_type FROM event_publications WHERE repository_id = ? AND version_id = ? AND symbol_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            EventPublication(
                symbol_id=SymbolId(row["symbol_id"]),
                event_id=EventId(row["event_id"]),
                publication_type=EventPublicationType(row["publication_type"])
            )
            for row in cur.fetchall()
        )

    def get_event_consumers(self, event_id: EventId) -> tuple[EventSubscription, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT symbol_id, event_id, subscription_type FROM event_subscriptions WHERE repository_id = ? AND version_id = ? AND event_id = ?",
            (repo_id, version_id, int(event_id))
        )
        return tuple(
            EventSubscription(
                symbol_id=SymbolId(row["symbol_id"]),
                event_id=EventId(row["event_id"]),
                subscription_type=EventSubscriptionType(row["subscription_type"])
            )
            for row in cur.fetchall()
        )

    def get_tests(self, symbol_id: SymbolId) -> tuple[TestRelationship, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT test_symbol_id, target_symbol_id, relationship_type FROM test_relationships WHERE repository_id = ? AND version_id = ? AND target_symbol_id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        return tuple(
            TestRelationship(
                test_symbol_id=SymbolId(row["test_symbol_id"]),
                target_symbol_id=SymbolId(row["target_symbol_id"]),
                relationship_type=TestRelationshipType(row["relationship_type"])
            )
            for row in cur.fetchall()
        )

    def close(self) -> None:
        self.conn.close()
