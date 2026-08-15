import sqlite3
import datetime
from typing import Any
from engine.repository.query.types import (
    Call,
    DatabaseRelationship,
    Endpoint,
    EventPublication,
    EventSubscription,
    File,
    FileId,
    Import,
    Reference,
    Symbol,
    SymbolId,
    EventId,
    EndpointId,
    EndpointMethod,
    EventSubscriptionType,
    EventPublicationType,
    DatabaseRelationshipType,
    CallType,
    ReferenceType,
    ImportType,
    TestRelationship,
    TestRelationshipType,
    TypeRelationship,
    TypeRelationshipType,
)
from engine.repository.model.repository_model import EntryPoint, EntryPointKind
from engine.repository.model.evidence import Evidence, FileLocation

from .store import RepositoryStore
from .schema import CREATE_TABLES_SQL, CREATE_INDEXES_SQL
from .errors import RepositoryNotFoundError, VersionNotFoundError


class SQLiteRepositoryStore(RepositoryStore):
    """
    SQLite-backed persistent implementation of RepositoryStore.
    
    Scopes all reads and writes to the set version context (repository_id, version_id).
    Supports logical views with parent version inheritance.
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
        self.parent_version_id: str | None = None

    def create_repository(self, provider: str, owner: str, name: str) -> str:
        repo_id = f"{provider}/{owner}/{name}"
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO repositories (id, provider, owner, name) VALUES (?, ?, ?, ?)",
                (repo_id, provider, owner, name)
            )
        return repo_id

    def create_version(self, repository_id: str, commit_sha: str, parent_sha: str | None = None) -> str:
        version_id = f"{repository_id}@{commit_sha}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        parent_version_id = None
        if parent_sha:
            parent_version_id = f"{repository_id}@{parent_sha}"
            
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO repository_versions (id, repository_id, commit_sha, parent_sha, parent_version_id, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (version_id, repository_id, commit_sha, parent_sha, parent_version_id, created_at, "pending")
            )
        return version_id

    def set_version_context(self, repository_id: str, version_id: str) -> None:
        # Verify existence
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM repositories WHERE id = ?", (repository_id,))
        if not cur.fetchone():
            raise RepositoryNotFoundError(f"Repository {repository_id} not found.")
            
        cur.execute("SELECT parent_version_id FROM repository_versions WHERE id = ?", (version_id,))
        row = cur.fetchone()
        if not row:
            raise VersionNotFoundError(f"Version {version_id} not found.")
            
        self.repository_id = repository_id
        self.version_id = version_id
        self.parent_version_id = row["parent_version_id"]

    def _get_context(self) -> tuple[str, str]:
        if self.repository_id is None or self.version_id is None:
            raise RuntimeError("Repository and version context must be set before executing queries.")
        return self.repository_id, self.version_id

    def delete_file_facts(self, repository_id: str, version_id: str, file_id: int) -> None:
        """Atomically delete all facts associated with a file in a version."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM symbols WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM calls WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM \"references\" WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM imports WHERE repository_id = ? AND version_id = ? AND source_file_id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM type_relationships WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM endpoints WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM database_relationships WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM event_publications WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM event_subscriptions WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id)
            )
            self.conn.execute(
                "DELETE FROM test_relationships WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id)
            )

    def _get_active_file_version(self, file_id: int) -> str | None:
        """Determines which version context (V, P, or None) should be used for a file."""
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        
        cur.execute(
            "SELECT state FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, version_id, file_id)
        )
        row = cur.fetchone()
        if row:
            return version_id if row["state"] == "active" else None
            
        if self.parent_version_id:
            cur.execute(
                "SELECT state FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                (repo_id, self.parent_version_id, file_id)
            )
            row = cur.fetchone()
            if row and row["state"] == "active":
                return self.parent_version_id
                
        return None

    def _get_symbol_resolved_version(self, symbol_id: SymbolId) -> tuple[str | None, int | None]:
        """Looks up symbol_id in logical view. Returns (resolved_version_id, file_id)."""
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        
        cur.execute(
            "SELECT file_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, version_id, int(symbol_id))
        )
        row = cur.fetchone()
        if row:
            file_id = row["file_id"]
            cur.execute(
                "SELECT state FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                (repo_id, version_id, file_id)
            )
            frow = cur.fetchone()
            if frow and frow["state"] == "active":
                return version_id, file_id
            return None, None
            
        if self.parent_version_id:
            cur.execute(
                "SELECT file_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id = ?",
                (repo_id, self.parent_version_id, int(symbol_id))
            )
            row = cur.fetchone()
            if row:
                file_id = row["file_id"]
                cur.execute(
                    "SELECT 1 FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                    (repo_id, version_id, file_id)
                )
                if not cur.fetchone():
                    cur.execute(
                        "SELECT state FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                        (repo_id, self.parent_version_id, file_id)
                    )
                    frow = cur.fetchone()
                    if frow and frow["state"] == "active":
                        return self.parent_version_id, file_id
                        
        return None, None

    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return None
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, file_id, kind, language, start_line, end_line, visibility, parent_symbol_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, resolved_version, int(symbol_id))
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
        repo_id, _ = self._get_context()
        resolved_version = self._get_active_file_version(int(file_id))
        if not resolved_version:
            return None
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, path, language FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, resolved_version, int(file_id))
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
            "SELECT caller_id, callee_id, call_type FROM calls c "
            "JOIN files f ON c.repository_id = f.repository_id AND c.version_id = f.version_id AND c.file_id = f.id "
            "WHERE c.repository_id = ? AND c.version_id = ? AND c.callee_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(symbol_id))
        )
        v_calls = [
            Call(
                caller_id=SymbolId(row["caller_id"]),
                callee_id=SymbolId(row["callee_id"]),
                call_type=CallType(row["call_type"])
            )
            for row in cur.fetchall()
        ]
        
        if self.parent_version_id:
            cur.execute(
                "SELECT caller_id, callee_id, call_type FROM calls c "
                "WHERE c.repository_id = ? AND c.version_id = ? AND c.callee_id = ? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM files f_v "
                "  WHERE f_v.repository_id = ? AND f_v.version_id = ? AND f_v.id = c.file_id"
                ")",
                (repo_id, self.parent_version_id, int(symbol_id), repo_id, version_id)
            )
            p_calls = [
                Call(
                    caller_id=SymbolId(row["caller_id"]),
                    callee_id=SymbolId(row["callee_id"]),
                    call_type=CallType(row["call_type"])
                )
                for row in cur.fetchall()
            ]
            return tuple(v_calls + p_calls)
            
        return tuple(v_calls)

    def get_callees(self, symbol_id: SymbolId) -> tuple[Call, ...]:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return ()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT caller_id, callee_id, call_type FROM calls WHERE repository_id = ? AND version_id = ? AND caller_id = ?",
            (repo_id, resolved_version, int(symbol_id))
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
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return ()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_id, target_id, relation_type FROM \"references\" WHERE repository_id = ? AND version_id = ? AND source_id = ?",
            (repo_id, resolved_version, int(symbol_id))
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
            "SELECT source_id, target_id, relation_type FROM \"references\" r "
            "JOIN files f ON r.repository_id = f.repository_id AND r.version_id = f.version_id AND r.file_id = f.id "
            "WHERE r.repository_id = ? AND r.version_id = ? AND r.target_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(symbol_id))
        )
        v_refs = [
            Reference(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relation_type=ReferenceType(row["relation_type"])
            )
            for row in cur.fetchall()
        ]
        
        if self.parent_version_id:
            cur.execute(
                "SELECT source_id, target_id, relation_type FROM \"references\" r "
                "WHERE r.repository_id = ? AND r.version_id = ? AND r.target_id = ? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM files f_v "
                "  WHERE f_v.repository_id = ? AND f_v.version_id = ? AND f_v.id = r.file_id"
                ")",
                (repo_id, self.parent_version_id, int(symbol_id), repo_id, version_id)
            )
            p_refs = [
                Reference(
                    source_id=SymbolId(row["source_id"]),
                    target_id=SymbolId(row["target_id"]),
                    relation_type=ReferenceType(row["relation_type"])
                )
                for row in cur.fetchall()
            ]
            return tuple(v_refs + p_refs)
            
        return tuple(v_refs)

    def get_imports(self, file_id: FileId) -> tuple[Import, ...]:
        repo_id, _ = self._get_context()
        resolved_version = self._get_active_file_version(int(file_id))
        if not resolved_version:
            return ()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_file_id, target_file_id, module, imported_name, import_type FROM imports WHERE repository_id = ? AND version_id = ? AND source_file_id = ?",
            (repo_id, resolved_version, int(file_id))
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
            "SELECT source_file_id, target_file_id, module, imported_name, import_type FROM imports i "
            "JOIN files f ON i.repository_id = f.repository_id AND i.version_id = f.version_id AND i.source_file_id = f.id "
            "WHERE i.repository_id = ? AND i.version_id = ? AND i.target_file_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(file_id))
        )
        v_imports = [
            Import(
                source_file_id=FileId(row["source_file_id"]),
                target_file_id=FileId(row["target_file_id"]) if row["target_file_id"] is not None else None,
                module=row["module"],
                imported_name=row["imported_name"],
                import_type=ImportType(row["import_type"])
            )
            for row in cur.fetchall()
        ]
        
        if self.parent_version_id:
            cur.execute(
                "SELECT source_file_id, target_file_id, module, imported_name, import_type FROM imports i "
                "WHERE i.repository_id = ? AND i.version_id = ? AND i.target_file_id = ? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM files f_v "
                "  WHERE f_v.repository_id = ? AND f_v.version_id = ? AND f_v.id = i.source_file_id"
                ")",
                (repo_id, self.parent_version_id, int(file_id), repo_id, version_id)
            )
            p_imports = [
                Import(
                    source_file_id=FileId(row["source_file_id"]),
                    target_file_id=FileId(row["target_file_id"]) if row["target_file_id"] is not None else None,
                    module=row["module"],
                    imported_name=row["imported_name"],
                    import_type=ImportType(row["import_type"])
                )
                for row in cur.fetchall()
            ]
            return tuple(v_imports + p_imports)
            
        return tuple(v_imports)

    def get_type_relationships(self, symbol_id: SymbolId) -> tuple[TypeRelationship, ...]:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return ()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_id, target_id, relationship_type FROM type_relationships WHERE repository_id = ? AND version_id = ? AND source_id = ?",
            (repo_id, resolved_version, int(symbol_id))
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
            "SELECT source_id, target_id, relationship_type FROM type_relationships tr "
            "JOIN files f ON tr.repository_id = f.repository_id AND tr.version_id = f.version_id AND tr.file_id = f.id "
            "WHERE tr.repository_id = ? AND tr.version_id = ? AND tr.target_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(symbol_id))
        )
        v_rels = [
            TypeRelationship(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relationship_type=TypeRelationshipType(row["relationship_type"])
            )
            for row in cur.fetchall()
        ]
        
        if self.parent_version_id:
            cur.execute(
                "SELECT source_id, target_id, relationship_type FROM type_relationships tr "
                "WHERE tr.repository_id = ? AND tr.version_id = ? AND tr.target_id = ? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM files f_v "
                "  WHERE f_v.repository_id = ? AND f_v.version_id = ? AND f_v.id = tr.file_id"
                ")",
                (repo_id, self.parent_version_id, int(symbol_id), repo_id, version_id)
            )
            p_rels = [
                TypeRelationship(
                    source_id=SymbolId(row["source_id"]),
                    target_id=SymbolId(row["target_id"]),
                    relationship_type=TypeRelationshipType(row["relationship_type"])
                )
                for row in cur.fetchall()
            ]
            return tuple(v_rels + p_rels)
            
        return tuple(v_rels)

    def get_endpoints(self, symbol_id: SymbolId) -> tuple[Endpoint, ...]:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return ()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, symbol_id, method, path, framework FROM endpoints WHERE repository_id = ? AND version_id = ? AND symbol_id = ?",
            (repo_id, resolved_version, int(symbol_id))
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
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return ()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT symbol_id, resource_id, relationship_type FROM database_relationships WHERE repository_id = ? AND version_id = ? AND symbol_id = ?",
            (repo_id, resolved_version, int(symbol_id))
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
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return ()
        cur = self.conn.cursor()
        cur.execute(
            "SELECT symbol_id, event_id, publication_type FROM event_publications WHERE repository_id = ? AND version_id = ? AND symbol_id = ?",
            (repo_id, resolved_version, int(symbol_id))
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
            "SELECT symbol_id, event_id, subscription_type FROM event_subscriptions es "
            "JOIN files f ON es.repository_id = f.repository_id AND es.version_id = f.version_id AND es.file_id = f.id "
            "WHERE es.repository_id = ? AND es.version_id = ? AND es.event_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(event_id))
        )
        v_subs = [
            EventSubscription(
                symbol_id=SymbolId(row["symbol_id"]),
                event_id=EventId(row["event_id"]),
                subscription_type=EventSubscriptionType(row["subscription_type"])
            )
            for row in cur.fetchall()
        ]
        
        if self.parent_version_id:
            cur.execute(
                "SELECT symbol_id, event_id, subscription_type FROM event_subscriptions es "
                "WHERE es.repository_id = ? AND es.version_id = ? AND es.event_id = ? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM files f_v "
                "  WHERE f_v.repository_id = ? AND f_v.version_id = ? AND f_v.id = es.file_id"
                ")",
                (repo_id, self.parent_version_id, int(event_id), repo_id, version_id)
            )
            p_subs = [
                EventSubscription(
                    symbol_id=SymbolId(row["symbol_id"]),
                    event_id=EventId(row["event_id"]),
                    subscription_type=EventSubscriptionType(row["subscription_type"])
                )
                for row in cur.fetchall()
            ]
            return tuple(v_subs + p_subs)
            
        return tuple(v_subs)

    def get_tests(self, symbol_id: SymbolId) -> tuple[TestRelationship, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        
        cur.execute(
            "SELECT test_symbol_id, target_symbol_id, relationship_type FROM test_relationships tr "
            "JOIN files f ON tr.repository_id = f.repository_id AND tr.version_id = f.version_id AND tr.file_id = f.id "
            "WHERE tr.repository_id = ? AND tr.version_id = ? AND tr.target_symbol_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(symbol_id))
        )
        v_tests = [
            TestRelationship(
                test_symbol_id=SymbolId(row["test_symbol_id"]),
                target_symbol_id=SymbolId(row["target_symbol_id"]),
                relationship_type=TestRelationshipType(row["relationship_type"])
            )
            for row in cur.fetchall()
        ]
        
        if self.parent_version_id:
            cur.execute(
                "SELECT test_symbol_id, target_symbol_id, relationship_type FROM test_relationships tr "
                "WHERE tr.repository_id = ? AND tr.version_id = ? AND tr.target_symbol_id = ? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM files f_v "
                "  WHERE f_v.repository_id = ? AND f_v.version_id = ? AND f_v.id = tr.file_id"
                ")",
                (repo_id, self.parent_version_id, int(symbol_id), repo_id, version_id)
            )
            p_tests = [
                TestRelationship(
                    test_symbol_id=SymbolId(row["test_symbol_id"]),
                    target_symbol_id=SymbolId(row["target_symbol_id"]),
                    relationship_type=TestRelationshipType(row["relationship_type"])
                )
                for row in cur.fetchall()
            ]
            return tuple(v_tests + p_tests)
            
        return tuple(v_tests)

    def get_entry_points(self) -> tuple[EntryPoint, ...]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        entry_points = []
        
        # 1. Fetch Endpoints
        cur.execute(
            "SELECT symbol_id, method, path, framework FROM endpoints WHERE repository_id = ? AND version_id = ?",
            (repo_id, version_id)
        )
        for row in cur.fetchall():
            sym_id = str(row["symbol_id"])
            route = f"{row['method']} {row['path']}"
            entry_points.append(EntryPoint(
                kind=EntryPointKind.REST_ENDPOINT,
                route=route,
                handler_id=sym_id,
                metadata={"framework": row["framework"], "method": row["method"], "path": row["path"]}
            ))
            
        # 2. Fetch Event Subscriptions (Event Consumers)
        cur.execute(
            "SELECT symbol_id, event_id, subscription_type FROM event_subscriptions WHERE repository_id = ? AND version_id = ?",
            (repo_id, version_id)
        )
        for row in cur.fetchall():
            sym_id = str(row["symbol_id"])
            event_id = str(row["event_id"])
            entry_points.append(EntryPoint(
                kind=EntryPointKind.EVENT_CONSUMER,
                route=f"event:{event_id}",
                handler_id=sym_id,
                metadata={"subscription_type": row["subscription_type"], "event_id": event_id}
            ))
            
        return tuple(entry_points)

    def close(self) -> None:
        self.conn.close()
