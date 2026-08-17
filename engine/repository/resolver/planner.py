from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Collection, Tuple, Set, Protocol

from engine.repository.store import RepositoryStore
from engine.repository.query import SymbolId, FileId, EventId
from integrations.base import RepositoryProvider
from .requirements import (
    ResolutionRequirement,
    FileResolutionRequirement,
    SymbolResolutionRequirement,
    EventResolutionRequirement,
    AllEntryPointsRequirement,
)
from .materialization.request import MaterializationRequest

# ---------------------------------------------------------------------------
# Planner contract (protocol)
# ---------------------------------------------------------------------------

class RequirementPlanner(Protocol):
    """Protocol for planning which repository paths need to be materialized.

    Implementations must provide an async ``plan`` method that receives a
    collection of ``ResolutionRequirement`` objects and returns one or more
    :class:`MaterializationRequest` instances.
    """

    async def plan(
        self,
        repository_id: str,
        commit_sha: str,
        requirements: Collection[ResolutionRequirement],
    ) -> Tuple[MaterializationRequest, ...]:
        ...

# ---------------------------------------------------------------------------
# Default implementation – retains legacy behaviour for now
# ---------------------------------------------------------------------------

class DefaultRequirementPlanner:
    """Concrete planner used by the resolver.

    For the initial phase we keep the behaviour of the previous planner but
    adapt the return type to ``MaterializationRequest``.  Future work will replace
    the rule‑based logic with the ``engine.repository.resolver.planning`` package.
    """

    def __init__(self, store: RepositoryStore, source: RepositoryProvider) -> None:
        self.store = store
        self.source = source

    # ---------------------------------------------------------------------
    # Helper methods – largely identical to the previous implementation
    # ---------------------------------------------------------------------

    def _get_path_from_file_id(self, repository_id: str, commit_sha: str, file_ref: FileId | str) -> str | None:
        """Resolve a ``FileId`` or raw path string to a relative file path."""
        if isinstance(file_ref, str):
            return file_ref
        file_obj = self.store.get_file(file_ref)
        if file_obj:
            return file_obj.path
        return None

    def _get_path_from_symbol_id(self, repository_id: str, commit_sha: str, symbol_id: SymbolId) -> str | None:
        """Find the file that defines the given symbol, if known."""
        symbol = self.store.get_symbol(symbol_id)
        if symbol:
            return self._get_path_from_file_id(repository_id, commit_sha, symbol.file_id)
        return None

    def _get_all_tree_entries(self, repository_id: str, commit_sha: str) -> dict[str, dict[str, object]]:
        """Return a dict mapping path → metadata for every entry in the repo tree.

        The store may expose a low‑level SQLite connection; we fall back to an empty
        dict if that attribute is missing.
        """
        if hasattr(self.store, "conn"):
            cur = self.store.conn.cursor()
            cur.execute(
                "SELECT path, type, blob_sha, size FROM repository_tree WHERE repository_id = ? AND commit_sha = ?",
                (repository_id, commit_sha),
            )
            return {
                row["path"]: {"path": row["path"], "type": row["type"], "blob_sha": row["blob_sha"], "size": row["size"]}
                for row in cur.fetchall()
            }
        return {}

    # ---------------------------------------------------------------------
    # Core planning entry‑point
    # ---------------------------------------------------------------------

    async def plan(
        self,
        repository_id: str,
        commit_sha: str,
        requirements: Collection[ResolutionRequirement],
    ) -> Tuple[MaterializationRequest, ...]:
        """Generate ``MaterializationRequest`` objects for a batch of requirements.

        The current implementation mirrors the legacy behaviour: it gathers a set
        of candidate file paths and returns a single request with reason
        ``"resolution"``.  The result is deterministic because the paths are
        sorted before constructing the request.
        """
        paths_to_materialize: Set[str] = set()

        for req in requirements:
            if isinstance(req, FileResolutionRequirement):
                await self._plan_file(repository_id, commit_sha, req, paths_to_materialize)
            elif isinstance(req, SymbolResolutionRequirement):
                await self._plan_symbol(repository_id, commit_sha, req, paths_to_materialize)
            elif isinstance(req, EventResolutionRequirement):
                await self._plan_event(repository_id, commit_sha, req, paths_to_materialize)
            elif isinstance(req, AllEntryPointsRequirement):
                await self._plan_all_entry_points(repository_id, commit_sha, paths_to_materialize)

        request = MaterializationRequest(
            repository_id=repository_id,
            commit_sha=commit_sha,
            paths=tuple(sorted(paths_to_materialize)),
            reason="resolution",
        )
        return (request,)

    # ---------------------------------------------------------------------
    # Individual planning helpers (unchanged from previous version)
    # ---------------------------------------------------------------------

    async def _plan_file(
        self,
        repository_id: str,
        commit_sha: str,
        req: FileResolutionRequirement,
        paths: Set[str],
    ) -> None:
        path = self._get_path_from_file_id(repository_id, commit_sha, req.file_id)
        if not path:
            return
        if req.query_type in ("file", "symbols"):
            if not self.store.is_materialized(repository_id, commit_sha, path):
                paths.add(path)
        elif req.query_type == "importers":
            coverage = self.store.get_materialization_coverage(repository_id, commit_sha)
            if coverage.materialized_files < coverage.known_files:
                await self._scan_for_imports(repository_id, commit_sha, path, paths)

    async def _plan_symbol(
        self,
        repository_id: str,
        commit_sha: str,
        req: SymbolResolutionRequirement,
        paths: Set[str],
    ) -> None:
        def_path = self._get_path_from_symbol_id(repository_id, commit_sha, req.symbol_id)
        if def_path and not self.store.is_materialized(repository_id, commit_sha, def_path):
            paths.add(def_path)
        if req.query_type in ("callers", "references_to", "type_dependents", "tests"):
            symbol_obj = self.store.get_symbol(req.symbol_id)
            if not symbol_obj:
                return
            coverage = self.store.get_materialization_coverage(repository_id, commit_sha)
            if coverage.materialized_files < coverage.known_files:
                await self._scan_for_symbol_references(
                    repository_id, commit_sha, symbol_obj.name, def_path, paths
                )

    async def _plan_event(
        self,
        repository_id: str,
        commit_sha: str,
        req: EventResolutionRequirement,
        paths: Set[str],
    ) -> None:
        coverage = self.store.get_materialization_coverage(repository_id, commit_sha)
        if coverage.materialized_files < coverage.known_files:
            await self._scan_for_event_subscribers(repository_id, commit_sha, req.event_id, paths)

    async def _plan_all_entry_points(
        self,
        repository_id: str,
        commit_sha: str,
        paths: Set[str],
    ) -> None:
        coverage = self.store.get_materialization_coverage(repository_id, commit_sha)
        if coverage.materialized_files < coverage.known_files:
            await self._scan_for_entry_points(repository_id, commit_sha, paths)

    # ---------------------------------------------------------------------
    # Scanning helpers – unchanged
    # ---------------------------------------------------------------------

    async def _scan_for_imports(
        self,
        repository_id: str,
        commit_sha: str,
        target_path: str,
        paths: Set[str],
    ) -> None:
        base_name = os.path.basename(target_path)
        module_name, _ = os.path.splitext(base_name)
        if not module_name:
            return
        tree_entries = self._get_all_tree_entries(repository_id, commit_sha)
        unmaterialized = [
            p for p, entry in tree_entries.items()
            if entry.get("type") == "blob" and not self.store.is_materialized(repository_id, commit_sha, p)
        ]
        batch_size = 50
        for i in range(0, len(unmaterialized), batch_size):
            batch = unmaterialized[i : i + batch_size]
            blobs = await self.source.get_files(repository_id, batch, commit_sha)
            for blob in blobs:
                try:
                    content = blob.content.decode("utf-8", errors="ignore")
                    if module_name in content:
                        paths.add(blob.path)
                except Exception:
                    pass

    async def _scan_for_symbol_references(
        self,
        repository_id: str,
        commit_sha: str,
        symbol_name: str,
        def_path: str | None,
        paths: Set[str],
    ) -> None:
        tree_entries = self._get_all_tree_entries(repository_id, commit_sha)
        unmaterialized = [
            p for p, entry in tree_entries.items()
            if entry.get("type") == "blob" and not self.store.is_materialized(repository_id, commit_sha, p)
        ]
        batch_size = 50
        for i in range(0, len(unmaterialized), batch_size):
            batch = unmaterialized[i : i + batch_size]
            blobs = await self.source.get_files(repository_id, batch, commit_sha)
            for blob in blobs:
                try:
                    content = blob.content.decode("utf-8", errors="ignore")
                    if symbol_name in content:
                        paths.add(blob.path)
                except Exception:
                    pass

    async def _scan_for_event_subscribers(
        self,
        repository_id: str,
        commit_sha: str,
        event_id: EventId | int | str,
        paths: Set[str],
    ) -> None:
        tree_entries = self._get_all_tree_entries(repository_id, commit_sha)
        unmaterialized = [
            p for p, entry in tree_entries.items()
            if entry.get("type") == "blob" and not self.store.is_materialized(repository_id, commit_sha, p)
        ]
        event_str = str(event_id)
        batch_size = 50
        for i in range(0, len(unmaterialized), batch_size):
            batch = unmaterialized[i : i + batch_size]
            blobs = await self.source.get_files(repository_id, batch, commit_sha)
            for blob in blobs:
                try:
                    content = blob.content.decode("utf-8", errors="ignore")
                    if event_str in content or "subscribe" in content or "consumer" in content:
                        paths.add(blob.path)
                except Exception:
                    pass

    async def _scan_for_entry_points(
        self,
        repository_id: str,
        commit_sha: str,
        paths: Set[str],
    ) -> None:
        tree_entries = self._get_all_tree_entries(repository_id, commit_sha)
        unmaterialized = [
            p for p, entry in tree_entries.items()
            if entry.get("type") == "blob" and not self.store.is_materialized(repository_id, commit_sha, p)
        ]
        batch_size = 50
        for i in range(0, len(unmaterialized), batch_size):
            batch = unmaterialized[i : i + batch_size]
            blobs = await self.source.get_files(repository_id, batch, commit_sha)
            for blob in blobs:
                try:
                    content = blob.content.decode("utf-8", errors="ignore")
                    if any(kw in content for kw in ("@app.", "FastAPI", "Blueprint", "def main", "if __name__")):
                        paths.add(blob.path)
                except Exception:
                    pass
