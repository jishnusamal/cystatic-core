import datetime
import sqlite3
from typing import Any, Sequence

from engine.repository.model.repository_model import EntryPoint, EntryPointKind
from engine.repository.query.types import (
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

from .errors import RepositoryNotFoundError, VersionNotFoundError
from .schema import CREATE_INDEXES_SQL, CREATE_TABLES_SQL
from .store import (
    MaterializationCoverage,
    MaterializationRecord,
    MaterializationStats,
    RepositoryStore,
)
from engine.repository.query.types import QueryResult


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

        # Migration logic
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM files")
            has_files = cur.fetchone()[0] > 0
            cur.execute("SELECT COUNT(*) FROM repository_materialization")
            has_materialization = cur.fetchone()[0] > 0
            if has_files and not has_materialization:
                # Backpopulate repository_materialization from files
                with self.conn:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO repository_materialization (repository_id, commit_sha, path, blob_sha, indexed_status, indexed_at) "
                        "SELECT f.repository_id, COALESCE(NULLIF(SUBSTR(f.version_id, INSTR(f.version_id, '@') + 1), ''), 'unknown'), f.path, '', 'indexed', ? "
                        "FROM files f",
                        (datetime.datetime.now(datetime.UTC).isoformat(),)
                    )
        except Exception:
            pass

        self.repository_id: str | None = None
        self.version_id: str | None = None
        self.parent_version_id: str | None = None

    def create_repository(self, provider: str, owner: str, name: str) -> str:
        repo_id = f"{provider}/{owner}/{name}"
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO repositories (id, provider, owner, name) VALUES (?, ?, ?, ?)",
                (repo_id, provider, owner, name),
            )
        return repo_id

    def create_version(
        self, repository_id: str, commit_sha: str, parent_sha: str | None = None
    ) -> str:
        version_id = f"{repository_id}@{commit_sha}"
        created_at = datetime.datetime.now(datetime.UTC).isoformat()

        parent_version_id = None
        if parent_sha:
            parent_version_id = f"{repository_id}@{parent_sha}"

        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO repository_versions (id, repository_id, commit_sha, parent_sha, parent_version_id, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    repository_id,
                    commit_sha,
                    parent_sha,
                    parent_version_id,
                    created_at,
                    "pending",
                ),
            )
        return version_id

    def set_version_context(self, repository_id: str, version_id: str) -> None:
        # Verify existence
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM repositories WHERE id = ?", (repository_id,))
        if not cur.fetchone():
            raise RepositoryNotFoundError(f"Repository {repository_id} not found.")

        cur.execute(
            "SELECT parent_version_id FROM repository_versions WHERE id = ?",
            (version_id,),
        )
        row = cur.fetchone()
        if not row:
            raise VersionNotFoundError(f"Version {version_id} not found.")

        self.repository_id = repository_id
        self.version_id = version_id
        self.parent_version_id = row["parent_version_id"]

    def _get_context(self) -> tuple[str, str]:
        if self.repository_id is None or self.version_id is None:
            raise RuntimeError(
                "Repository and version context must be set before executing queries."
            )
        return self.repository_id, self.version_id

    def delete_file_facts(
        self, repository_id: str, version_id: str, file_id: int
    ) -> None:
        """Atomically delete all facts associated with a file in a version."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                "DELETE FROM symbols WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                "DELETE FROM calls WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                'DELETE FROM "references" WHERE repository_id = ? AND version_id = ? AND file_id = ?',
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                "DELETE FROM imports WHERE repository_id = ? AND version_id = ? AND source_file_id = ?",
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                "DELETE FROM type_relationships WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                "DELETE FROM endpoints WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                "DELETE FROM database_relationships WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                "DELETE FROM event_publications WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                "DELETE FROM event_subscriptions WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id),
            )
            self.conn.execute(
                "DELETE FROM test_relationships WHERE repository_id = ? AND version_id = ? AND file_id = ?",
                (repository_id, version_id, file_id),
            )

    def _get_active_file_version(self, file_id: Any) -> tuple[str | None, int | None]:
        """Determines which version context (V, P, or None) and int file_id should be used."""
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()

        try:
            file_id_int = int(file_id)
            cur.execute(
                "SELECT state FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                (repo_id, version_id, file_id_int),
            )
            row = cur.fetchone()
            if row:
                return (version_id if row["state"] == "active" else None), file_id_int

            if self.parent_version_id:
                cur.execute(
                    "SELECT state FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                    (repo_id, self.parent_version_id, file_id_int),
                )
                row = cur.fetchone()
                if row and row["state"] == "active":
                    return self.parent_version_id, file_id_int

            return None, None
        except ValueError:
            cur.execute(
                "SELECT id, state FROM files WHERE repository_id = ? AND version_id = ? AND path = ?",
                (repo_id, version_id, str(file_id)),
            )
            row = cur.fetchone()
            if row:
                return (version_id if row["state"] == "active" else None), row["id"]

            if self.parent_version_id:
                cur.execute(
                    "SELECT id, state FROM files WHERE repository_id = ? AND version_id = ? AND path = ?",
                    (repo_id, self.parent_version_id, str(file_id)),
                )
                row = cur.fetchone()
                if row and row["state"] == "active":
                    return self.parent_version_id, row["id"]

            return None, None

    def _get_symbol_resolved_version(
        self, symbol_id: SymbolId
    ) -> tuple[str | None, int | None]:
        """Looks up symbol_id in logical view. Returns (resolved_version_id, file_id)."""
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()

        cur.execute(
            "SELECT file_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, version_id, int(symbol_id)),
        )
        row = cur.fetchone()
        if row:
            file_id = row["file_id"]
            cur.execute(
                "SELECT state FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                (repo_id, version_id, file_id),
            )
            frow = cur.fetchone()
            if frow and frow["state"] == "active":
                return version_id, file_id
            return None, None

        if self.parent_version_id:
            cur.execute(
                "SELECT file_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id = ?",
                (repo_id, self.parent_version_id, int(symbol_id)),
            )
            row = cur.fetchone()
            if row:
                file_id = row["file_id"]
                cur.execute(
                    "SELECT 1 FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                    (repo_id, version_id, file_id),
                )
                if not cur.fetchone():
                    cur.execute(
                        "SELECT state FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
                        (repo_id, self.parent_version_id, file_id),
                    )
                    frow = cur.fetchone()
                    if frow and frow["state"] == "active":
                        return self.parent_version_id, file_id

        return None, None

    def _is_indexing_complete(self) -> bool:
        repo_id, version_id = self._get_context()
        commit_sha = version_id.split("@")[-1]
        cur = self.conn.cursor()
        cur.execute(
            "SELECT indexed_complete FROM repository_metadata WHERE repository_id = ? AND commit_sha = ?",
            (repo_id, commit_sha),
        )
        row = cur.fetchone()
        return bool(row and row["indexed_complete"])

    def _is_file_indexed(self, file_id: FileId) -> bool:
        repo_id, _ = self._get_context()
        resolved_version, file_id_int = self._get_active_file_version(file_id)
        if not resolved_version or file_id_int is None:
            return False
            
        cur = self.conn.cursor()
        cur.execute(
            "SELECT path FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, resolved_version, file_id_int),
        )
        row = cur.fetchone()
        if not row:
            return False
        path = row["path"]
        commit_sha = resolved_version.split("@")[-1]
        
        cur.execute(
            "SELECT indexed_status FROM repository_materialization "
            "WHERE repository_id = ? AND commit_sha = ? AND path = ?",
            (repo_id, commit_sha, path),
        )
        mrow = cur.fetchone()
        return bool(mrow and mrow["indexed_status"] == "indexed")

    def _is_symbol_file_indexed(self, symbol_id: SymbolId) -> bool:
        repo_id, _ = self._get_context()
        resolved_version, file_id_int = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version or file_id_int is None:
            return False
        
        cur = self.conn.cursor()
        cur.execute(
            "SELECT path FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, resolved_version, file_id_int),
        )
        row = cur.fetchone()
        if not row:
            return False
        path = row["path"]
        commit_sha = resolved_version.split("@")[-1]
        
        cur.execute(
            "SELECT indexed_status FROM repository_materialization "
            "WHERE repository_id = ? AND commit_sha = ? AND path = ?",
            (repo_id, commit_sha, path),
        )
        mrow = cur.fetchone()
        return bool(mrow and mrow["indexed_status"] == "indexed")

    def is_materialized(
        self,
        repository_id: str,
        commit_sha: str,
        path: str,
    ) -> bool:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT indexed_status FROM repository_materialization "
            "WHERE repository_id = ? AND commit_sha = ? AND path = ?",
            (repository_id, commit_sha, path),
        )
        row = cur.fetchone()
        return bool(row and row["indexed_status"] == "indexed")

    def get_materialization(
        self,
        repository_id: str,
        commit_sha: str,
        path: str,
    ) -> MaterializationRecord | None:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT repository_id, commit_sha, path, blob_sha, indexed_status, indexed_at "
            "FROM repository_materialization "
            "WHERE repository_id = ? AND commit_sha = ? AND path = ?",
            (repository_id, commit_sha, path),
        )
        row = cur.fetchone()
        if not row:
            return None
        return MaterializationRecord(
            repository_id=row["repository_id"],
            commit_sha=row["commit_sha"],
            path=row["path"],
            blob_sha=row["blob_sha"],
            indexed_status=row["indexed_status"],
            indexed_at=row["indexed_at"],
        )

    def get_materialized_paths(
        self,
        repository_id: str,
        commit_sha: str,
    ) -> list[str]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT path FROM repository_materialization "
            "WHERE repository_id = ? AND commit_sha = ? AND indexed_status = 'indexed'",
            (repository_id, commit_sha),
        )
        return [row["path"] for row in cur.fetchall()]

    def get_materialization_stats(
        self,
        repository_id: str,
        commit_sha: str,
    ) -> MaterializationStats:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT "
            "  COUNT(*) as total, "
            "  SUM(CASE WHEN indexed_status = 'indexed' THEN 1 ELSE 0 END) as indexed, "
            "  SUM(CASE WHEN indexed_status = 'failed' THEN 1 ELSE 0 END) as failed, "
            "  SUM(CASE WHEN indexed_status = 'pending' THEN 1 ELSE 0 END) as pending "
            "FROM repository_materialization "
            "WHERE repository_id = ? AND commit_sha = ?",
            (repository_id, commit_sha),
        )
        row = cur.fetchone()
        return MaterializationStats(
            repository_id=repository_id,
            commit_sha=commit_sha,
            total_files=row["total"] or 0,
            indexed_files=row["indexed"] or 0,
            failed_files=row["failed"] or 0,
            pending_files=row["pending"] or 0,
        )

    def get_materialization_coverage(
        self,
        repository_id: str,
        commit_sha: str,
    ) -> MaterializationCoverage:
        cur = self.conn.cursor()
        
        cur.execute(
            "SELECT COUNT(*), SUM(size) FROM repository_tree "
            "WHERE repository_id = ? AND commit_sha = ?",
            (repository_id, commit_sha),
        )
        t_row = cur.fetchone()
        known_files = t_row[0] or 0
        known_bytes = t_row[1] or 0
        
        cur.execute(
            "SELECT COUNT(m.path), SUM(t.size) "
            "FROM repository_materialization m "
            "LEFT JOIN repository_tree t ON m.repository_id = t.repository_id "
            "  AND m.commit_sha = t.commit_sha AND m.path = t.path "
            "WHERE m.repository_id = ? AND m.commit_sha = ? AND m.indexed_status = 'indexed'",
            (repository_id, commit_sha),
        )
        m_row = cur.fetchone()
        materialized_files = m_row[0] or 0
        materialized_bytes = m_row[1] or 0
        
        return MaterializationCoverage(
            known_files=known_files,
            materialized_files=materialized_files,
            known_bytes=known_bytes,
            materialized_bytes=materialized_bytes,
        )

    def record_tree(
        self,
        repository_id: str,
        commit_sha: str,
        entries: Sequence[dict[str, Any]],
    ) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM repository_tree WHERE repository_id = ? AND commit_sha = ?",
                (repository_id, commit_sha),
            )
            self.conn.executemany(
                "INSERT INTO repository_tree (repository_id, commit_sha, path, type, blob_sha, size) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        repository_id,
                        commit_sha,
                        e["path"],
                        e.get("type", "file"),
                        e.get("blob_sha"),
                        e.get("size", 0),
                    )
                    for e in entries
                ],
            )
            self.conn.execute(
                "INSERT INTO repository_metadata (repository_id, commit_sha, tree_complete, indexed_complete) "
                "VALUES (?, ?, 1, 0) "
                "ON CONFLICT(repository_id, commit_sha) DO UPDATE SET tree_complete = 1",
                (repository_id, commit_sha),
            )

    def record_materialization(
        self,
        repository_id: str,
        commit_sha: str,
        path: str,
        blob_sha: str,
        indexed_status: str,
    ) -> None:
        indexed_at = datetime.datetime.now(datetime.UTC).isoformat()
        with self.conn:
            self.conn.execute(
                "INSERT INTO repository_materialization (repository_id, commit_sha, path, blob_sha, indexed_status, indexed_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(repository_id, commit_sha, path) DO UPDATE SET "
                "  blob_sha = excluded.blob_sha, "
                "  indexed_status = excluded.indexed_status, "
                "  indexed_at = excluded.indexed_at",
                (repository_id, commit_sha, path, blob_sha, indexed_status, indexed_at),
            )

    def set_indexed_complete(
        self,
        repository_id: str,
        commit_sha: str,
        indexed_complete: bool = True,
    ) -> None:
        val = 1 if indexed_complete else 0
        with self.conn:
            self.conn.execute(
                "INSERT INTO repository_metadata (repository_id, commit_sha, tree_complete, indexed_complete) "
                "VALUES (?, ?, 0, ?) "
                "ON CONFLICT(repository_id, commit_sha) DO UPDATE SET indexed_complete = excluded.indexed_complete",
                (repository_id, commit_sha, val),
            )

    def get_tree_entries(
        self,
        repository_id: str,
        commit_sha: str,
        paths: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        if not paths:
            return {}
        cur = self.conn.cursor()
        results = {}
        paths_list = list(paths)
        chunk_size = 999
        for i in range(0, len(paths_list), chunk_size):
            chunk = paths_list[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            cur.execute(
                f"SELECT path, type, blob_sha, size FROM repository_tree "
                f"WHERE repository_id = ? AND commit_sha = ? AND path IN ({placeholders})",
                (repository_id, commit_sha, *chunk),
            )
            for row in cur.fetchall():
                results[row["path"]] = {
                    "path": row["path"],
                    "type": row["type"],
                    "blob_sha": row["blob_sha"],
                    "size": row["size"],
                }
        return results

    def get_symbol(self, symbol_id: SymbolId) -> Symbol | None:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return None
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, file_id, kind, language, start_line, end_line, visibility, parent_symbol_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, resolved_version, int(symbol_id)),
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
            parent_symbol_id=SymbolId(row["parent_symbol_id"])
            if row["parent_symbol_id"] is not None
            else None,
        )

    def get_symbols(self, symbol_ids: list[SymbolId]) -> QueryResult[Symbol]:
        if not symbol_ids:
            return QueryResult((), complete=True)
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()

        # Determine logical version for each symbol ID
        placeholders = ",".join("?" for _ in symbol_ids)
        cur.execute(
            f"SELECT id, file_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id IN ({placeholders})",
            (repo_id, version_id) + tuple(int(sid) for sid in symbol_ids),
        )
        current_rows = cur.fetchall()
        resolved_map = {}
        file_ids_to_check = set()
        symbol_files = {}

        for row in current_rows:
            sid = SymbolId(row["id"])
            fid = row["file_id"]
            symbol_files[sid] = fid
            file_ids_to_check.add(fid)
            resolved_map[sid] = version_id

        remaining_ids = [sid for sid in symbol_ids if sid not in resolved_map]
        if remaining_ids and self.parent_version_id:
            placeholders_rem = ",".join("?" for _ in remaining_ids)
            cur.execute(
                f"SELECT id, file_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id IN ({placeholders_rem})",
                (repo_id, self.parent_version_id) + tuple(int(sid) for sid in remaining_ids),
            )
            parent_rows = cur.fetchall()
            for row in parent_rows:
                sid = SymbolId(row["id"])
                fid = row["file_id"]
                symbol_files[sid] = fid
                file_ids_to_check.add(fid)
                resolved_map[sid] = self.parent_version_id

        # Validate active file states
        active_files = set()
        if file_ids_to_check:
            placeholders_files = ",".join("?" for _ in file_ids_to_check)
            cur.execute(
                f"SELECT id, state FROM files WHERE repository_id = ? AND version_id = ? AND id IN ({placeholders_files})",
                (repo_id, version_id) + tuple(file_ids_to_check),
            )
            files_in_current = {row["id"]: row["state"] for row in cur.fetchall()}

            files_not_in_current = file_ids_to_check - set(files_in_current.keys())
            files_in_parent = {}
            if files_not_in_current and self.parent_version_id:
                placeholders_parent_files = ",".join("?" for _ in files_not_in_current)
                cur.execute(
                    f"SELECT id, state FROM files WHERE repository_id = ? AND version_id = ? AND id IN ({placeholders_parent_files})",
                    (repo_id, self.parent_version_id) + tuple(files_not_in_current),
                )
                files_in_parent = {row["id"]: row["state"] for row in cur.fetchall()}

            for fid in file_ids_to_check:
                if fid in files_in_current:
                    if files_in_current[fid] == "active":
                        active_files.add(fid)
                elif fid in files_in_parent:
                    if files_in_parent[fid] == "active":
                        active_files.add(fid)

        final_resolved = {
            sid: vid
            for sid, vid in resolved_map.items()
            if symbol_files.get(sid) in active_files
        }

        if not final_resolved:
            is_complete = self._is_indexing_complete()
            return QueryResult((), complete=is_complete)

        results = []
        from collections import defaultdict
        by_version = defaultdict(list)
        for sid, vid in final_resolved.items():
            by_version[vid].append(sid)

        for vid, sids in by_version.items():
            placeholders_sids = ",".join("?" for _ in sids)
            cur.execute(
                f"SELECT id, name, file_id, kind, language, start_line, end_line, visibility, parent_symbol_id FROM symbols WHERE repository_id = ? AND version_id = ? AND id IN ({placeholders_sids})",
                (repo_id, vid) + tuple(int(sid) for sid in sids),
            )
            for row in cur.fetchall():
                results.append(
                    Symbol(
                        id=SymbolId(row["id"]),
                        name=row["name"],
                        file_id=FileId(row["file_id"]),
                        kind=SymbolKind(row["kind"]),
                        language=row["language"],
                        start_line=row["start_line"],
                        end_line=row["end_line"],
                        visibility=SymbolVisibility(row["visibility"]),
                        parent_symbol_id=SymbolId(row["parent_symbol_id"])
                        if row["parent_symbol_id"] is not None
                        else None,
                    )
                )

        is_complete = self._is_indexing_complete()
        if not is_complete:
            all_found_indexed = len(final_resolved) == len(symbol_ids)
            for sid in final_resolved:
                if not self._is_symbol_file_indexed(sid):
                    all_found_indexed = False
                    break
            if all_found_indexed:
                is_complete = True

        return QueryResult(tuple(results), complete=is_complete)

    def get_file(self, file_id: FileId) -> File | None:
        repo_id, _ = self._get_context()
        resolved_version, file_id_int = self._get_active_file_version(file_id)
        if not resolved_version or file_id_int is None:
            return None
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, path, language FROM files WHERE repository_id = ? AND version_id = ? AND id = ?",
            (repo_id, resolved_version, file_id_int),
        )
        row = cur.fetchone()
        if not row:
            return None
        return File(id=FileId(row["id"]), path=row["path"], language=row["language"])

    def get_callers(self, symbol_id: SymbolId) -> QueryResult[Call]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()

        cur.execute(
            "SELECT caller_id, callee_id, call_type FROM calls c "
            "JOIN files f ON c.repository_id = f.repository_id AND c.version_id = f.version_id AND c.file_id = f.id "
            "WHERE c.repository_id = ? AND c.version_id = ? AND c.callee_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(symbol_id)),
        )
        v_calls = [
            Call(
                caller_id=SymbolId(row["caller_id"]),
                callee_id=SymbolId(row["callee_id"]),
                call_type=CallType(row["call_type"]),
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
                (repo_id, self.parent_version_id, int(symbol_id), repo_id, version_id),
            )
            p_calls = [
                Call(
                    caller_id=SymbolId(row["caller_id"]),
                    callee_id=SymbolId(row["callee_id"]),
                    call_type=CallType(row["call_type"]),
                )
                for row in cur.fetchall()
            ]
            return QueryResult(tuple(v_calls + p_calls), complete=self._is_indexing_complete())

        return QueryResult(tuple(v_calls), complete=self._is_indexing_complete())

    def get_callees(self, symbol_id: SymbolId) -> QueryResult[Call]:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return QueryResult((), complete=self._is_indexing_complete())
        cur = self.conn.cursor()
        cur.execute(
            "SELECT caller_id, callee_id, call_type FROM calls WHERE repository_id = ? AND version_id = ? AND caller_id = ?",
            (repo_id, resolved_version, int(symbol_id)),
        )
        facts = tuple(
            Call(
                caller_id=SymbolId(row["caller_id"]),
                callee_id=SymbolId(row["callee_id"]),
                call_type=CallType(row["call_type"]),
            )
            for row in cur.fetchall()
        )
        return QueryResult(facts, complete=self._is_symbol_file_indexed(symbol_id))

    def get_references_from(self, symbol_id: SymbolId) -> QueryResult[Reference]:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return QueryResult((), complete=self._is_indexing_complete())
        cur = self.conn.cursor()
        cur.execute(
            'SELECT source_id, target_id, relation_type FROM "references" WHERE repository_id = ? AND version_id = ? AND source_id = ?',
            (repo_id, resolved_version, int(symbol_id)),
        )
        facts = tuple(
            Reference(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relation_type=ReferenceType(row["relation_type"]),
            )
            for row in cur.fetchall()
        )
        return QueryResult(facts, complete=self._is_symbol_file_indexed(symbol_id))

    def get_references_to(self, symbol_id: SymbolId) -> QueryResult[Reference]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()

        cur.execute(
            'SELECT source_id, target_id, relation_type FROM "references" r '
            "JOIN files f ON r.repository_id = f.repository_id AND r.version_id = f.version_id AND r.file_id = f.id "
            "WHERE r.repository_id = ? AND r.version_id = ? AND r.target_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(symbol_id)),
        )
        v_refs = [
            Reference(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relation_type=ReferenceType(row["relation_type"]),
            )
            for row in cur.fetchall()
        ]

        if self.parent_version_id:
            cur.execute(
                'SELECT source_id, target_id, relation_type FROM "references" r '
                "WHERE r.repository_id = ? AND r.version_id = ? AND r.target_id = ? "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM files f_v "
                "  WHERE f_v.repository_id = ? AND f_v.version_id = ? AND f_v.id = r.file_id"
                ")",
                (repo_id, self.parent_version_id, int(symbol_id), repo_id, version_id),
            )
            p_refs = [
                Reference(
                    source_id=SymbolId(row["source_id"]),
                    target_id=SymbolId(row["target_id"]),
                    relation_type=ReferenceType(row["relation_type"]),
                )
                for row in cur.fetchall()
            ]
            return QueryResult(tuple(v_refs + p_refs), complete=self._is_indexing_complete())

        return QueryResult(tuple(v_refs), complete=self._is_indexing_complete())

    def get_imports(self, file_id: FileId) -> QueryResult[Import]:
        repo_id, _ = self._get_context()
        resolved_version, file_id_int = self._get_active_file_version(file_id)
        if not resolved_version or file_id_int is None:
            return QueryResult((), complete=self._is_indexing_complete())
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_file_id, target_file_id, module, imported_name, import_type FROM imports WHERE repository_id = ? AND version_id = ? AND source_file_id = ?",
            (repo_id, resolved_version, file_id_int),
        )
        facts = tuple(
            Import(
                source_file_id=FileId(row["source_file_id"]),
                target_file_id=FileId(row["target_file_id"])
                if row["target_file_id"] is not None
                else None,
                module=row["module"],
                imported_name=row["imported_name"],
                import_type=ImportType(row["import_type"]),
            )
            for row in cur.fetchall()
        )
        return QueryResult(facts, complete=self._is_file_indexed(file_id))

    def get_importers(self, file_id: FileId) -> QueryResult[Import]:
        repo_id, version_id = self._get_context()
        try:
            file_id_int = int(file_id)
        except ValueError:
            f = self.get_file(file_id)
            if not f:
                return QueryResult((), complete=self._is_indexing_complete())
            file_id_int = int(f.id)

        cur = self.conn.cursor()

        cur.execute(
            "SELECT source_file_id, target_file_id, module, imported_name, import_type FROM imports i "
            "JOIN files f ON i.repository_id = f.repository_id AND i.version_id = f.version_id AND i.source_file_id = f.id "
            "WHERE i.repository_id = ? AND i.version_id = ? AND i.target_file_id = ? AND f.state = 'active'",
            (repo_id, version_id, file_id_int),
        )

        v_imports = [
            Import(
                source_file_id=FileId(row["source_file_id"]),
                target_file_id=FileId(row["target_file_id"])
                if row["target_file_id"] is not None
                else None,
                module=row["module"],
                imported_name=row["imported_name"],
                import_type=ImportType(row["import_type"]),
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
                (repo_id, self.parent_version_id, int(file_id), repo_id, version_id),
            )
            p_imports = [
                Import(
                    source_file_id=FileId(row["source_file_id"]),
                    target_file_id=FileId(row["target_file_id"])
                    if row["target_file_id"] is not None
                    else None,
                    module=row["module"],
                    imported_name=row["imported_name"],
                    import_type=ImportType(row["import_type"]),
                )
                for row in cur.fetchall()
            ]
            return QueryResult(tuple(v_imports + p_imports), complete=self._is_indexing_complete())

        return QueryResult(tuple(v_imports), complete=self._is_indexing_complete())

    def get_type_relationships(
        self, symbol_id: SymbolId
    ) -> QueryResult[TypeRelationship]:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return QueryResult((), complete=self._is_indexing_complete())
        cur = self.conn.cursor()
        cur.execute(
            "SELECT source_id, target_id, relationship_type FROM type_relationships WHERE repository_id = ? AND version_id = ? AND source_id = ?",
            (repo_id, resolved_version, int(symbol_id)),
        )
        facts = tuple(
            TypeRelationship(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relationship_type=TypeRelationshipType(row["relationship_type"]),
            )
            for row in cur.fetchall()
        )
        return QueryResult(facts, complete=self._is_symbol_file_indexed(symbol_id))

    def get_type_dependents(self, symbol_id: SymbolId) -> QueryResult[TypeRelationship]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()

        cur.execute(
            "SELECT source_id, target_id, relationship_type FROM type_relationships tr "
            "JOIN files f ON tr.repository_id = f.repository_id AND tr.version_id = f.version_id AND tr.file_id = f.id "
            "WHERE tr.repository_id = ? AND tr.version_id = ? AND tr.target_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(symbol_id)),
        )
        v_rels = [
            TypeRelationship(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relationship_type=TypeRelationshipType(row["relationship_type"]),
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
                (repo_id, self.parent_version_id, int(symbol_id), repo_id, version_id),
            )
            p_rels = [
                TypeRelationship(
                    source_id=SymbolId(row["source_id"]),
                    target_id=SymbolId(row["target_id"]),
                    relationship_type=TypeRelationshipType(row["relationship_type"]),
                )
                for row in cur.fetchall()
            ]
            return QueryResult(tuple(v_rels + p_rels), complete=self._is_indexing_complete())

        return QueryResult(tuple(v_rels), complete=self._is_indexing_complete())

    def get_endpoints(self, symbol_id: SymbolId) -> QueryResult[Endpoint]:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return QueryResult((), complete=self._is_indexing_complete())
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, symbol_id, method, path, framework FROM endpoints WHERE repository_id = ? AND version_id = ? AND symbol_id = ?",
            (repo_id, resolved_version, int(symbol_id)),
        )
        facts = tuple(
            Endpoint(
                id=EndpointId(row["id"]),
                symbol_id=SymbolId(row["symbol_id"]),
                method=EndpointMethod(row["method"]),
                path=row["path"],
                framework=row["framework"],
            )
            for row in cur.fetchall()
        )
        return QueryResult(facts, complete=self._is_symbol_file_indexed(symbol_id))

    def get_database_relationships(
        self, symbol_id: SymbolId
    ) -> QueryResult[DatabaseRelationship]:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return QueryResult((), complete=self._is_indexing_complete())
        cur = self.conn.cursor()
        cur.execute(
            "SELECT symbol_id, resource_id, relationship_type FROM database_relationships WHERE repository_id = ? AND version_id = ? AND symbol_id = ?",
            (repo_id, resolved_version, int(symbol_id)),
        )
        facts = tuple(
            DatabaseRelationship(
                symbol_id=SymbolId(row["symbol_id"]),
                resource_id=ResourceId(row["resource_id"]),
                relationship_type=DatabaseRelationshipType(row["relationship_type"]),
            )
            for row in cur.fetchall()
        )
        return QueryResult(facts, complete=self._is_symbol_file_indexed(symbol_id))

    def get_published_events(self, symbol_id: SymbolId) -> QueryResult[EventPublication]:
        repo_id, _ = self._get_context()
        resolved_version, _ = self._get_symbol_resolved_version(symbol_id)
        if not resolved_version:
            return QueryResult((), complete=self._is_indexing_complete())
        cur = self.conn.cursor()
        cur.execute(
            "SELECT symbol_id, event_id, publication_type FROM event_publications WHERE repository_id = ? AND version_id = ? AND symbol_id = ?",
            (repo_id, resolved_version, int(symbol_id)),
        )
        facts = tuple(
            EventPublication(
                symbol_id=SymbolId(row["symbol_id"]),
                event_id=EventId(row["event_id"]),
                publication_type=EventPublicationType(row["publication_type"]),
            )
            for row in cur.fetchall()
        )
        return QueryResult(facts, complete=self._is_symbol_file_indexed(symbol_id))

    def get_event_consumers(self, event_id: EventId) -> QueryResult[EventSubscription]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()

        cur.execute(
            "SELECT symbol_id, event_id, subscription_type FROM event_subscriptions es "
            "JOIN files f ON es.repository_id = f.repository_id AND es.version_id = f.version_id AND es.file_id = f.id "
            "WHERE es.repository_id = ? AND es.version_id = ? AND es.event_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(event_id)),
        )
        v_subs = [
            EventSubscription(
                symbol_id=SymbolId(row["symbol_id"]),
                event_id=EventId(row["event_id"]),
                subscription_type=EventSubscriptionType(row["subscription_type"]),
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
                (repo_id, self.parent_version_id, int(event_id), repo_id, version_id),
            )
            p_subs = [
                EventSubscription(
                    symbol_id=SymbolId(row["symbol_id"]),
                    event_id=EventId(row["event_id"]),
                    subscription_type=EventSubscriptionType(row["subscription_type"]),
                )
                for row in cur.fetchall()
            ]
            return QueryResult(tuple(v_subs + p_subs), complete=self._is_indexing_complete())

        return QueryResult(tuple(v_subs), complete=self._is_indexing_complete())

    def get_tests(self, symbol_id: SymbolId) -> QueryResult[TestRelationship]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()

        cur.execute(
            "SELECT test_symbol_id, target_symbol_id, relationship_type FROM test_relationships tr "
            "JOIN files f ON tr.repository_id = f.repository_id AND tr.version_id = f.version_id AND tr.file_id = f.id "
            "WHERE tr.repository_id = ? AND tr.version_id = ? AND tr.target_symbol_id = ? AND f.state = 'active'",
            (repo_id, version_id, int(symbol_id)),
        )
        v_tests = [
            TestRelationship(
                test_symbol_id=SymbolId(row["test_symbol_id"]),
                target_symbol_id=SymbolId(row["target_symbol_id"]),
                relationship_type=TestRelationshipType(row["relationship_type"]),
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
                (repo_id, self.parent_version_id, int(symbol_id), repo_id, version_id),
            )
            p_tests = [
                TestRelationship(
                    test_symbol_id=SymbolId(row["test_symbol_id"]),
                    target_symbol_id=SymbolId(row["target_symbol_id"]),
                    relationship_type=TestRelationshipType(row["relationship_type"]),
                )
                for row in cur.fetchall()
            ]
            return QueryResult(tuple(v_tests + p_tests), complete=self._is_indexing_complete())

        return QueryResult(tuple(v_tests), complete=self._is_indexing_complete())

    def get_entry_points(self) -> QueryResult[EntryPoint]:
        repo_id, version_id = self._get_context()
        cur = self.conn.cursor()
        entry_points = []

        # 1. Fetch Endpoints
        cur.execute(
            "SELECT symbol_id, method, path, framework FROM endpoints WHERE repository_id = ? AND version_id = ?",
            (repo_id, version_id),
        )
        for row in cur.fetchall():
            sym_id = str(row["symbol_id"])
            route = f"{row['method']} {row['path']}"
            entry_points.append(
                EntryPoint(
                    kind=EntryPointKind.REST_ENDPOINT,
                    route=route,
                    handler_id=sym_id,
                    metadata={
                        "framework": row["framework"],
                        "method": row["method"],
                        "path": row["path"],
                    },
                )
            )

        # 2. Fetch Event Subscriptions (Event Consumers)
        cur.execute(
            "SELECT symbol_id, event_id, subscription_type FROM event_subscriptions WHERE repository_id = ? AND version_id = ?",
            (repo_id, version_id),
        )
        for row in cur.fetchall():
            sym_id = str(row["symbol_id"])
            event_id = str(row["event_id"])
            entry_points.append(
                EntryPoint(
                    kind=EntryPointKind.EVENT_CONSUMER,
                    route=f"event:{event_id}",
                    handler_id=sym_id,
                    metadata={
                        "subscription_type": row["subscription_type"],
                        "event_id": event_id,
                    },
                )
            )

        return QueryResult(tuple(entry_points), complete=self._is_indexing_complete())

    def get_symbols_in_file(self, file_id: FileId) -> QueryResult[Symbol]:
        repo_id, _ = self._get_context()
        resolved_version, file_id_int = self._get_active_file_version(file_id)
        if not resolved_version or file_id_int is None:
            return QueryResult((), complete=self._is_indexing_complete())

        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name, file_id, kind, language, start_line, end_line, visibility, parent_symbol_id "
            "FROM symbols WHERE repository_id = ? AND version_id = ? AND file_id = ?",
            (repo_id, resolved_version, file_id_int),
        )
        symbols = [
            Symbol(
                id=SymbolId(row["id"]),
                name=row["name"],
                file_id=FileId(row["file_id"]),
                kind=SymbolKind(row["kind"]),
                language=row["language"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                visibility=SymbolVisibility(row["visibility"]),
                parent_symbol_id=SymbolId(row["parent_symbol_id"])
                if row["parent_symbol_id"] is not None
                else None,
            )
            for row in cur.fetchall()
        ]
        return QueryResult(tuple(symbols), complete=self._is_file_indexed(file_id))

    def close(self) -> None:
        self.conn.close()
