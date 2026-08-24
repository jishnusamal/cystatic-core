from __future__ import annotations

import gc
import os
import time
from dataclasses import dataclass
from typing import Any

from core.logging import pipeline_logger
from engine.change.passes.file_classification import (
    DEFAULT_ANALYSIS_POLICY,
    AnalysisPolicy,
    FileClassification,
    FileClassifier,
    detect_language,
)
from engine.language.base import FileContext
from engine.repository.indexing.indexer import RepositoryIndexer
from engine.repository.metrics import RepositoryMaterializationMetrics
from engine.repository.store import RepositoryStore
from integrations.base import RepositoryProvider

from .budget import MaterializationBudget
from .request import MaterializationRequest


@dataclass(frozen=True)
class MaterializationResult:
    """Immutable result from a materialization operation."""
    requested_paths: tuple[str, ...]
    materialized_paths: tuple[str, ...]
    already_materialized_paths: tuple[str, ...]
    failed_paths: tuple[str, ...]
    bytes_fetched: int
    facts_generated: int
    # Paths excluded from analysis by file-role classification. Distinct from
    # failed paths: excluded ≠ missing ≠ failed materialization.
    excluded_paths: tuple[str, ...] = ()
    excluded_classifications: dict[str, str] | None = None


def normalize_path(path: str) -> str:
    """Normalize file path to POSIX-style relative to repository root."""
    p = path.replace("\\", "/")
    normalized = os.path.normpath(p).replace("\\", "/")
    normalized = normalized.removeprefix("./")
    if normalized == "." or normalized == "":
        normalized = ""
    return normalized


class RepositoryMaterializer:
    """Responsible for turning requested repository paths into persisted facts."""

    def __init__(
        self,
        source: RepositoryProvider,
        store: RepositoryStore,
        indexer: RepositoryIndexer,
        budget: MaterializationBudget,
        metrics: RepositoryMaterializationMetrics,
        materialization_batch_size: int = 100,
        classifier: FileClassifier | None = None,
        policy: AnalysisPolicy | None = None,
    ) -> None:
        self.source = source
        self.store = store
        self.indexer = indexer
        self.budget = budget
        self.metrics = metrics
        self.materialization_batch_size = materialization_batch_size
        # Reuses the same classification the ChangeCompiler applies, so files
        # analysis would ignore are never fetched from the remote provider.
        self.classifier = classifier or FileClassifier()
        self.policy = policy or DEFAULT_ANALYSIS_POLICY

    def _emit_event(self, event: str, **kwargs: Any) -> None:
        """Emit a structured event to the profiling/logging system."""
        import json
        ctx = pipeline_logger.current_context
        if ctx and hasattr(ctx, "log_manager") and ctx.log_manager:
            ctx.log_manager.log_structured_event(
                phase="repository",
                event=event,
                to_terminal=True,
                **kwargs,
            )
        else:
            payload = {
                "phase": "repository",
                "event": event,
                **kwargs,
            }
            pipeline_logger.log_pipeline(json.dumps(payload), to_terminal=True)

    async def materialize(self, request: MaterializationRequest) -> MaterializationResult:
        """Materialize requested files: fetch, parse, index, and persist facts."""
        start_time = time.perf_counter()
        self.metrics.reason = request.reason

        # 1. Emit started event
        self._emit_event(
            "repository_materialization_started",
            repository=request.repository_id,
            commit=request.commit_sha,
            reason=request.reason,
            requested=len(request.paths),
        )

        try:
            # 2. Normalize and deduplicate requested paths
            normalized_paths = tuple(
                sorted({normalize_path(p) for p in request.paths if p})
            )
            self.metrics.requested_files = len(request.paths)
            self.metrics.deduplicated_files = len(normalized_paths)

            # Ensure version context and registration exists in store
            version_id = self.store.create_version(request.repository_id, request.commit_sha)
            self.store.set_version_context(request.repository_id, version_id)

            # Dynamically bind the indexer sink to the requested version
            if hasattr(self.indexer, "sink") and self.indexer.sink:
                if hasattr(self.indexer.sink, "repository_id"):
                    self.indexer.sink.repository_id = request.repository_id
                if hasattr(self.indexer.sink, "version_id"):
                    self.indexer.sink.version_id = version_id

            # 3. Query repository tree entries to validate paths and get expected info
            tree_entries = self.store.get_tree_entries(
                request.repository_id, request.commit_sha, normalized_paths
            )

            already_materialized = []
            to_materialize = []
            failed_paths = []

            for path in normalized_paths:
                entry = tree_entries.get(path)
                if not entry or entry.get("type") != "blob":
                    # Path does not exist in repo tree or is not a file
                    failed_paths.append(path)
                    continue

                expected_sha = entry.get("blob_sha")
                expected_size = entry.get("size", 0)

                # Check existing materialization in store
                mat = self.store.get_materialization(
                    request.repository_id, request.commit_sha, path
                )
                if mat and mat.indexed_status == "indexed" and mat.blob_sha == expected_sha:
                    already_materialized.append(path)
                else:
                    to_materialize.append((path, expected_sha, expected_size))

            self.metrics.already_materialized_files = len(already_materialized)

            # 3.5 File role classification — reuse ChangeCompiler's eligibility
            #     policy BEFORE any remote fetch so excluded files (e.g.
            #     frontend TS/TSX, generated files) never cost network I/O or
            #     materialization budget.
            excluded_paths = []
            excluded_classifications: dict[str, str] = {}
            eligible_to_materialize = []
            for path, expected_sha, expected_size in to_materialize:
                classification: FileClassification = self.classifier.classify(path)
                self.metrics.record_classification(classification.kind.value)
                if not self.policy.should_materialize(
                    classification, detect_language(path)
                ):
                    excluded_paths.append(path)
                    excluded_classifications[path] = classification.kind.value
                    self.metrics.record_excluded_file(
                        path=path, kind=classification.kind.value
                    )
                    # Persist the exclusion explicitly: excluded ≠ missing ≠ failed.
                    self.store.record_materialization(
                        request.repository_id,
                        request.commit_sha,
                        path,
                        expected_sha,
                        "excluded",
                    )
                else:
                    eligible_to_materialize.append((path, expected_sha, expected_size))

            to_materialize = eligible_to_materialize
            self.metrics.eligible_files = (
                len(already_materialized) + len(to_materialize)
            )

            # 4. Budget is enforced pre-materialization by RepositoryResolver.
            #    The materializer receives only batches that have already passed
            #    the ResolutionContext.can_materialize() check.  We keep the
            #    batch_size variable for internal batching below.
            batch_size = self.materialization_batch_size

            # Initialize / update coverage metrics
            coverage = self.store.get_materialization_coverage(
                request.repository_id, request.commit_sha
            )
            self.metrics.set_repository_size(
                files=coverage.known_files, bytes=coverage.known_bytes
            )

            # Pre-populate metrics with already materialized paths from store
            already_indexed = self.store.get_materialized_paths(
                request.repository_id, request.commit_sha
            )
            already_indexed_entries = self.store.get_tree_entries(
                request.repository_id, request.commit_sha, already_indexed
            )
            for path in already_indexed:
                size = 0
                if path in already_indexed_entries:
                    size = already_indexed_entries[path].get("size", 0)
                self.metrics.record_file(path=path, size=size)

            materialized_paths = []
            bytes_fetched = 0
            facts_generated_before = self.metrics.facts_generated

            # 5. Fetch, index, and persist in batches
            batches = [
                to_materialize[i : i + batch_size]
                for i in range(0, len(to_materialize), batch_size)
            ]

            for idx, batch in enumerate(batches):
                batch_start = time.perf_counter()
                batch_paths = [p for p, _, _ in batch]

                acq_start = time.perf_counter()
                blobs = await self.source.get_files(
                    request.repository_id, batch_paths, request.commit_sha
                )
                acq_duration = time.perf_counter() - acq_start
                self.metrics.repository_acquisition_ms += acq_duration * 1000.0
                self.metrics.remote_requests += 1

                files_to_index = {}
                blob_by_path = {}

                for blob in blobs:
                    blob_by_path[blob.path] = blob
                    try:
                        content_str = blob.content.decode("utf-8")
                        # Construct FileContext (point 14: convert blob to FileContext)
                        _ = FileContext(
                            path=blob.path,
                            source=content_str,
                            ast=None,
                            language="",
                        )
                        files_to_index[blob.path] = content_str
                        bytes_fetched += len(blob.content)
                        self.metrics.files_fetched += 1
                        self.metrics.bytes_fetched += len(blob.content)
                    except (UnicodeDecodeError, UnicodeError):
                        # Skip binary file
                        failed_paths.append(blob.path)

                fetched_paths = set(blob_by_path.keys())
                for path in batch_paths:
                    if path not in fetched_paths:
                        failed_paths.append(path)

                # Index files individually to preserve successful work on partial failure
                idx_start = time.perf_counter()
                indexed_in_batch = 0

                for file_path, content in files_to_index.items():
                    blob = blob_by_path[file_path]
                    try:
                        self.indexer.index_files(
                            {file_path: content},
                            metrics=self.metrics,
                        )
                        materialized_paths.append(file_path)
                        indexed_in_batch += 1
                        self.metrics.record_file(path=file_path, size=len(blob.content))
                    except Exception:  # noqa: BLE001 -- indexer records failed state and rolls back
                        # Indexer already records failed state in DB and rolls back
                        failed_paths.append(file_path)

                idx_duration = time.perf_counter() - idx_start
                self.metrics.repository_indexing_ms += idx_duration * 1000.0

                # Emit batch event
                self._emit_event(
                    "repository_materialization_batch",
                    repository=request.repository_id,
                    commit=request.commit_sha,
                    reason=request.reason,
                    batch_index=idx,
                    batch_files=batch_paths,
                    fetched=len(blobs),
                    indexed=indexed_in_batch,
                    bytes=sum(len(b.content) for b in blobs),
                    duration=time.perf_counter() - batch_start,
                )

                # Aggressively release source/AST objects from memory
                del files_to_index
                del blob_by_path
                del blobs
                gc.collect()

            duration = time.perf_counter() - start_time
            self.metrics.duration = duration

            # 6. Emit completed event
            self._emit_event(
                "repository_materialization_completed",
                repository=request.repository_id,
                commit=request.commit_sha,
                reason=request.reason,
                requested=len(request.paths),
                fetched=self.metrics.files_fetched,
                indexed=len(materialized_paths),
                bytes=bytes_fetched,
                excluded=len(excluded_paths),
                duration=duration,
            )

            return MaterializationResult(
                requested_paths=request.paths,
                materialized_paths=tuple(materialized_paths),
                already_materialized_paths=tuple(already_materialized),
                failed_paths=tuple(failed_paths),
                bytes_fetched=bytes_fetched,
                facts_generated=self.metrics.facts_generated - facts_generated_before,
                excluded_paths=tuple(sorted(excluded_paths)),
                excluded_classifications=excluded_classifications,
            )

        except Exception as e:
            duration = time.perf_counter() - start_time
            self.metrics.duration = duration
            # Emit failed event
            self._emit_event(
                "repository_materialization_failed",
                repository=request.repository_id,
                commit=request.commit_sha,
                reason=request.reason,
                error=str(e),
                duration=duration,
            )
            raise
