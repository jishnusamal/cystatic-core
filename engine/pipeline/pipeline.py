"""Pipeline orchestrator - the runtime execution engine.

Orchestrates the complete flow from repository/diff to OperationalChangeModel.
No compiler logic - pure orchestration.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

import tiktoken

from core.errors import (
    DiffFetchFailed,
    InvalidDiff,
    PipelineExecutionError,
    RepositoryCompilationFailed,
    RepositoryNotInstalled,
)
from core.logging import timer
from core.runtime import PREVENT_LEGACY_ARCHITECTURE
from engine.behavior.compiler import BehaviorCompiler
from engine.change.compiler import ChangeCompiler
from engine.change.model.repository_comparison import RepositoryComparison
from engine.language.detection import LanguageDetector
from engine.language.base import FileContext
from engine.language.registry import LanguageRegistry
from engine.llm_context.compiler import LLMContextCompiler
from engine.operational.compiler import (
    EngineeringDiscoveryCompiler,
    OperationalCompiler,
)
from engine.operational.discovery import DiscoveryCompiler
from engine.pipeline.context import PipelineContext
from engine.repository.facts import File
from engine.repository.indexing import InMemoryFactSink, RepositoryIndexer
from engine.repository.overlay import RepositoryOverlay, RepositoryView
from engine.repository.query import InMemoryRepository, RepositoryQuery
from engine.repository.store import (
    PersistentFactSink,
    RepositoryStore,
    SQLiteRepositoryStore,
)
from engine.review_context.compiler import ReviewContextCompiler
from integrations.github.renderers.github_renderer import GitHubRenderer
from integrations.github.renderers.json_renderer import JSONRenderer
from models import AnalysisRequest


# Custom print wrapper to avoid polluting stdout
def print(*args, **kwargs):
    sep = kwargs.get("sep", " ")
    msg = sep.join(str(arg) for arg in args)
    from core.logging import pipeline_logger

    pipeline_logger.log_pipeline(msg, to_terminal=False)


if TYPE_CHECKING:
    from integrations.base import (
        OutputProvider,
        RepositoryProvider,
    )


class Pipeline:
    """
    Main pipeline orchestrator for runtime execution.

    Coordinates the complete flow:
    1. Repository compilation
    2. Change compilation
    3. Behavior compilation
    4. Operational compilation
    5. Rendering

    This is the runtime - no compiler logic lives here.

    Pipeline depends only on:
    - RepositoryProvider
    - Renderer
    - OutputProvider
    """

    def __init__(
        self,
        repository_store: RepositoryStore | None = None,
        language_registry: LanguageRegistry | None = None,
        repository_provider: RepositoryProvider | None = None,
        output_provider: OutputProvider | None = None,
    ) -> None:
        """
        Initialize the pipeline.

        Args:
            repository_store: Storage backend for repository facts
            language_registry: Language registry instance
            repository_provider: Provider for fetching repository data
            output_provider: Provider for publishing results
        """
        self.repository_store = repository_store or SQLiteRepositoryStore(
            "repository_store.db"
        )
        from engine.language.builtins import create_default_language_registry
        self.language_registry = language_registry or create_default_language_registry()
        self.repository_provider = repository_provider
        self.output_provider = output_provider

        # Compilers (reused across executions)
        self._change_compiler = ChangeCompiler()
        self._behavior_compiler = BehaviorCompiler()
        self._operational_compiler = OperationalCompiler()
        self._discovery_compiler = EngineeringDiscoveryCompiler()
        self._discovery_discovery_compiler = DiscoveryCompiler()
        self._review_context_compiler = ReviewContextCompiler()
        from core.config import get_compiler_settings

        self._llm_context_compiler = LLMContextCompiler(
            settings=get_compiler_settings()
        )

        # Renderers
        self._json_renderer = JSONRenderer()
        self._github_renderer: GitHubRenderer | None = None

    async def run(self, request: AnalysisRequest) -> PipelineContext:
        """
        Run the pipeline for an analysis request.

        Args:
            request: Analysis request with repository, PR, and diff info

        Returns:
            PipelineContext with all results
        """
        from datetime import datetime

        from core.logging import pipeline_logger
        from core.runtime import RunContext
        from engine.language.base.instrumentation import get_instrumentation

        started_at = datetime.now()
        run_context = RunContext.create(started_at=started_at)
        pipeline_logger.start_run(run_context)
        pipeline_start_time = time.perf_counter()

        from core.profile import get_current_profiler

        profiler = get_current_profiler()

        context = PipelineContext(
            run_context=run_context,
            repository=request.repository.full_name,
            base_sha=request.pull_request.base_sha if request.pull_request else None,
            head_sha=request.pull_request.head_sha if request.pull_request else None,
            request_id=request.metadata.get("delivery_id")
            if request.metadata
            else None,
        )

        repo_name = request.repository.full_name
        pr_num = str(request.pull_request.number) if request.pull_request else "N/A"

        banner = (
            "====================================================\n\n"
            "Factor Analysis\n\n"
            "Run ID:\n"
            f"{run_context.run_id}\n\n"
            "Repository:\n"
            f"{repo_name}\n\n"
            "PR:\n"
            f"{pr_num}\n\n"
            "Logs:\n\n"
            f"{run_context.log_dir}/\n\n"
            "===================================================="
        )
        pipeline_logger.log_pipeline(banner, to_terminal=True)

        arch_info = (
            "Repository architecture:\n"
            f"  store: {type(self.repository_store).__name__ if self.repository_store else 'None'}\n"
            "  view: RepositoryView\n"
            "  legacy_graph: false\n"
            "  repository_model: false\n"
            "  full_repo_download: false"
        )
        pipeline_logger.log_pipeline(arch_info, to_terminal=True)

        legacy_guard_token = PREVENT_LEGACY_ARCHITECTURE.set(True)

        try:
            context.mark_compilation_start()

            with timer.timed(
                "Total Pipeline", metadata={"repository": request.repository.full_name}
            ):
                # Step 1: Compile base facts & PR overlay
                print(
                    f"[pipeline] Step 1: Fact-based repository compilation for {request.repository.full_name}"
                )
                await self._compile_facts_and_view(context, request)
                print(
                    f"[pipeline] Step 1 done: language={context.language}, base_query={'set' if context.base_query else 'None'}, view={'set' if context.repository_view else 'None'}"
                )

                from core.profile import get_current_profiler

                profiler = get_current_profiler()
                if profiler:
                    profiler.log_memory("After repository facts & overlay load")

            # Step 2: Fetch diff if not provided
            if context.diff_data is None and request.has_diff:
                assert request.diff is not None
                context.diff_data = self._diff_snapshot_to_dict(request.diff)
                if context.diff_data is not None:
                    print(
                        f"[pipeline] Step 2: Diff provided in request, {len(context.diff_data.get('files', []))} files"
                    )

            if context.diff_data is None and self.repository_provider:
                print("[pipeline] Step 2: Fetching diff from provider")
                await self._fetch_diff(context, request)
                print(
                    f"[pipeline] Step 2 done: {len(context.diff_data.get('files', []))} files in diff"
                    if context.diff_data
                    else "[pipeline] Step 2 done: no diff"
                )

            # Step 3: Change Compilation
            change_start = time.perf_counter()
            with timer.timed("Change Compilation"):
                print("[pipeline] Step 3: Change facts compilation")
                capabilities = self._get_repository_capabilities(context)
                if capabilities.symbols:
                    await self._compile_change(context)
                else:
                    print("[pipeline] Step 3: symbols capability is False, skipping change compilation.")
                print("[pipeline] Step 3 done")
                timer.print_progress()
            change_time = time.perf_counter() - change_start
            if profiler:
                profiler.log_memory("After Change Compiler")

            # Step 4: Behavior Compilation
            behavior_start = time.perf_counter()
            with timer.timed("Behavior Compilation"):
                print("[pipeline] Step 4: Behavior model compilation")
                capabilities = self._get_repository_capabilities(context)
                if capabilities.calls and context.change_model is not None:
                    await self._compile_behavior(context)
                else:
                    print("[pipeline] Step 4: calls capability is False or change_model is None, skipping behavior compilation.")
                print("[pipeline] Step 4 done")
                timer.print_progress()
            behavior_time = time.perf_counter() - behavior_start
            if profiler:
                profiler.log_memory("After Behavior Compiler")

            # Step 5: Operational Compilation
            operational_start = time.perf_counter()
            with timer.timed("Operational Compilation"):
                print("[pipeline] Step 5: Operational model compilation")
                if context.change_model is not None and context.behavior_model is not None:
                    await self._compile_operational(context)
                else:
                    print("[pipeline] Step 5: missing change_model or behavior_model, skipping operational compilation.")
                print("[pipeline] Step 5 done")
                timer.print_progress()
            operational_time = time.perf_counter() - operational_start
            if profiler:
                profiler.log_memory("After Operational Compiler")

            # Step 6: Engineering Discovery Compilation
            discovery_start = time.perf_counter()
            with timer.timed("Engineering Discovery Compilation"):
                print("[pipeline] Step 6: Engineering discovery model compilation")
                if context.ocm is not None:
                    await self._compile_discovery(context)
                else:
                    print("[pipeline] Step 6: ocm is None, skipping engineering discovery compilation.")
                print("[pipeline] Step 6 done")
                timer.print_progress()
            discovery_time = time.perf_counter() - discovery_start
            if profiler:
                profiler.log_memory("After Engineering Discovery Compiler")

            # Step 7: Discovery IR Compilation
            discovery_ir_start = time.perf_counter()
            with timer.timed("Discovery IR Compilation"):
                print("[pipeline] Step 7: Discovery IR compilation")
                if context.edm is not None:
                    await self._compile_discovery_ir(context)
                else:
                    print("[pipeline] Step 7: edm is None, skipping discovery IR compilation.")
                print("[pipeline] Step 7 done")
                timer.print_progress()
            discovery_ir_time = time.perf_counter() - discovery_ir_start
            if profiler:
                profiler.log_memory("After Discovery IR Compiler")

            if profiler:
                profiler.log_memory("After system-model construction")

            # Step 8: ReviewContext Compilation
            review_start = time.perf_counter()
            with timer.timed("ReviewContext Compilation"):
                print("[pipeline] Step 8: ReviewContext compilation")
                await self._compile_review_context(context)
                print("[pipeline] Step 8 done")
                timer.print_progress()
            review_time = time.perf_counter() - review_start
            if profiler:
                profiler.log_memory("After ReviewContext Compiler")

            # Step 9: LLMContext Compilation
            llm_start = time.perf_counter()
            with timer.timed("LLMContext Compilation"):
                print("[pipeline] Step 9: LLMContext compilation")
                await self._compile_llm_context(context)
                print("[pipeline] Step 9 done")
                timer.print_progress()
            llm_time = time.perf_counter() - llm_start
            if profiler:
                profiler.log_memory("After LLMContext Compiler")

            if profiler:
                profiler.log_memory("After context generation")

            # Print timings to terminal in aligned format
            def format_time(seconds: float) -> str:
                if seconds < 1.0:
                    return f"{seconds * 1000:.0f}ms"
                return f"{seconds:.1f}s"

            def log_stage_time(stage_name: str, elapsed: float):
                time_str = format_time(elapsed)
                stage_text = f"[Pipeline] {stage_name}"
                pipeline_logger.log_pipeline(
                    f"{stage_text:<38}{time_str}", to_terminal=True
                )

            pipeline_logger.log_pipeline("", to_terminal=True)
            log_stage_time("Change compilation", change_time)
            log_stage_time("Behavior compilation", behavior_time)
            log_stage_time("Operational compilation", operational_time)
            log_stage_time("ReviewContext", review_time)
            log_stage_time("LLMContext", llm_time)

            pipeline_logger.log_pipeline("", to_terminal=True)
            total_time = time.perf_counter() - pipeline_start_time
            pipeline_logger.log_pipeline(f"Total: {total_time:.1f}s", to_terminal=True)

            # Repository materialization logging
            metrics = context.repository_materialization
            if metrics.repository_files == 0 and context.base_query is not None:
                base_files_count = 0
                if hasattr(context.base_query, "conn"):
                    try:
                        cur = context.base_query.conn.cursor()
                        repo_id_ctx, version_id_ctx = context.base_query._get_context()
                        cur.execute(
                            "SELECT COUNT(*) as count FROM files WHERE repository_id = ? AND version_id = ?",
                            (repo_id_ctx, version_id_ctx),
                        )
                        row = cur.fetchone()
                        if row:
                            base_files_count = row["count"]
                    except Exception:
                        pass
                elif hasattr(context.base_query, "_facts"):
                    base_files_count = len(context.base_query._facts.files)
                
                if base_files_count > 0:
                    metrics.set_repository_size(files=base_files_count, bytes=0)

            # JSON log
            import json
            log_payload = {
                "event": "repository_materialization",
                "repository": repo_name,
                "commit": context.base_sha or "unknown",
                **metrics.snapshot(),
            }
            pipeline_logger.log_pipeline(json.dumps(log_payload), to_terminal=False)

            # Human readable summary
            repo_mb = metrics.repository_bytes / (1024 * 1024)
            mat_mb = metrics.materialized_bytes / (1024 * 1024)
            human_summary = (
                "Repository materialization:\n"
                f"  repository: {repo_name}\n"
                f"  files: {metrics.materialized_files:,} / {metrics.repository_files:,} ({metrics.materialization_percent:.2f}%)\n"
                f"  bytes: {mat_mb:.2f} MB / {repo_mb:.2f} MB ({metrics.materialization_bytes_percent:.2f}%)"
            )
            pipeline_logger.log_pipeline(human_summary, to_terminal=True)

            context.mark_complete()

        except Exception as exc:
            context.error = exc
            context.mark_complete()
            elapsed_time = time.perf_counter() - pipeline_start_time
            if run_context and run_context.log_manager:
                run_context.log_manager.log_failure(
                    exc=exc,
                    phase="pipeline",
                    repository=repo_name,
                    pr=pr_num,
                    elapsed_time=elapsed_time,
                )
            else:
                pipeline_logger.log_pipeline(f"✗ {exc}", to_terminal=True)
            raise
        finally:
            timer.print_summary()
            pipeline_logger.write_to_disk()

            if run_context and run_context.log_manager:
                # Write summary.json
                summary_data = {
                    "run_id": run_context.run_id,
                    "started_at": run_context.started_at.isoformat(),
                    "completed_at": datetime.now().isoformat(),
                    "repository": repo_name,
                    "pr": pr_num,
                    "total_time_seconds": round(
                        time.perf_counter() - pipeline_start_time, 3
                    ),
                    "context": context.to_dict(),
                    "has_error": context.error is not None,
                    "error": str(context.error) if context.error else None,
                }
                run_context.log_manager.write_json("summary.json", summary_data)

                # Write profile.json
                inst = get_instrumentation()
                profile_data = {
                    "global_counters": inst.global_counters,
                    "pass_stats": {
                        name: {
                            "total_time": round(stats.total_time, 4),
                            "call_count": stats.call_count,
                            "max_time": round(stats.max_time, 4),
                            "min_time": round(stats.min_time, 4)
                            if stats.min_time != float("inf")
                            else 0,
                            "files_processed": stats.files_processed,
                            "counters": stats.counters,
                            "objects_emitted": stats.objects_emitted,
                        }
                        for name, stats in inst.pass_stats.items()
                    },
                }
                run_context.log_manager.write_json("profile.json", profile_data)

                # Close log manager
                run_context.log_manager.close()

            PREVENT_LEGACY_ARCHITECTURE.reset(legacy_guard_token)

        return context

    async def _compile_base_graph(
        self,
        request: AnalysisRequest,
        base_sha: str,
        context: PipelineContext,
    ) -> tuple[RepositoryGraph, float, float, str]:
        """Fetch and compile base repository graph in a local scope to ensure source release."""
        base_fetch_start = time.perf_counter()
        try:
            snapshot = await self.repository_provider.fetch_repository_at_sha(
                request.repository, base_sha
            )
        except Exception as exc:
            raise RepositoryCompilationFailed(
                f"Failed to fetch base repository at {base_sha}: {exc}",
                details={"repository": request.repository.full_name, "sha": base_sha},
            ) from exc
        base_fetch_time = time.perf_counter() - base_fetch_start
        context.base_repository_snapshot = snapshot
        print(f"[pipeline] Base snapshot fetched: {len(snapshot.files)} files")

        # Detect language
        if context.language is None:
            print(f"[pipeline] Detecting language from {len(snapshot.files)} files...")
            detector = LanguageDetector(self.language_registry)
            file_contexts = [
                FileContext(path=path, source=content, ast=None, language="")
                for path, content in snapshot.files.items()
            ]
            spec = detector.detect(file_contexts)
            language = spec.id
            context.language = language
            context.adapter = language
            print(f"[pipeline] Detected language: {language}")
        else:
            language = context.language

        plugin = self.language_registry.get(language)
        adapter = plugin.create_adapter()

        base_compile_start = time.perf_counter()
        repository_input = {
            "root_directory": request.repository.full_name,
            "language": language,
            "files": snapshot.files,
            "commit_sha": base_sha,
        }
        print("[pipeline] Compiling base RepositoryGraph...")
        try:
            from core.profile import get_current_profiler

            profiler = get_current_profiler()
            if profiler:
                profiler.log_memory("After base repository download")
            base_graph = adapter.compile_graph(repository_input)
        except Exception as exc:
            raise RepositoryCompilationFailed(
                f"Base repository compilation failed: {exc}",
                details={
                    "repository": request.repository.full_name,
                    "language": language,
                    "sha": base_sha,
                },
            ) from exc
        base_compile_time = time.perf_counter() - base_compile_start
        return base_graph, base_fetch_time, base_compile_time, language

    async def _compile_head_graph(
        self,
        request: AnalysisRequest,
        head_sha: str,
        base_graph: RepositoryGraph,
        language: str,
        context: PipelineContext,
    ) -> tuple[RepositoryGraph, float, float, float, float, dict[str, Any]]:
        """Fetch changed files and compile head repository graph incrementally in a local scope."""
        changed_fetch_start = time.perf_counter()
        changed_files_dict = {}

        if request.pull_request:
            if context.diff_data is None:
                if request.has_diff:
                    context.diff_data = self._diff_snapshot_to_dict(request.diff)
                else:
                    try:
                        await self._fetch_diff(context, request)
                    except Exception as exc:
                        raise DiffFetchFailed(
                            f"Failed to fetch diff: {exc}",
                            details={"repository": request.repository.full_name},
                        ) from exc

            # Fetch only changed files concurrently
            if context.diff_data and "files" in context.diff_data:

                async def fetch_one(file_path: str):
                    try:
                        if self.repository_provider is None:
                            return file_path, None
                        content = await self.repository_provider.fetch_file(
                            request.repository, file_path, head_sha
                        )
                        return file_path, content
                    except Exception as exc:
                        print(
                            f"[pipeline] File {file_path} not found at head (assumed deleted): {exc}"
                        )
                        return file_path, None

                tasks = [
                    fetch_one(file_info["file_path"])
                    for file_info in context.diff_data["files"]
                ]
                results = await asyncio.gather(*tasks)
                changed_files_dict = dict(results)

        changed_fetch_time = time.perf_counter() - changed_fetch_start

        from core.profile import get_current_profiler

        profiler = get_current_profiler()
        if profiler:
            profiler.log_memory("After GitHub/API data retrieval")
            profiler.log_memory("After head source load")

        # Clone base_graph using pickle to avoid mutating cache
        import pickle

        from core.logging import pipeline_logger

        pipeline_logger.log_pipeline(
            "[pipeline] Step 1.2: Cloning base RepositoryGraph for head compilation...",
            to_terminal=True,
        )
        clone_start = time.perf_counter()
        if profiler:
            profiler.log_memory("Before graph clone")
            profiler.start_sub_peak_tracking()
        patched_graph = pickle.loads(pickle.dumps(base_graph))
        if profiler:
            peak_during_clone = profiler.stop_sub_peak_tracking()
            profiler.checkpoints["peak during graph clone"] = {
                "current_rss": profiler.process.memory_info().rss / (1024 * 1024),
                "peak_rss": peak_during_clone,
            }
            profiler.log_memory("After graph clone")
        clone_duration = time.perf_counter() - clone_start
        pipeline_logger.log_pipeline(
            f"[pipeline] Step 1.2 done: Base graph cloned in {clone_duration:.2f}s",
            to_terminal=True,
        )

        # Compile changes incrementally on patched_graph
        metrics: dict[str, Any] = {}
        incremental_start = time.perf_counter()

        plugin = self.language_registry.get(language)
        adapter = plugin.create_adapter()
        repository_input = {
            "files": changed_files_dict,
            "changed_only": True,
            "metrics": metrics,
            "language": language,
        }

        pipeline_logger.log_pipeline(
            f"[pipeline] Step 1.3: Running incremental compilation for {len(changed_files_dict)} changed files...",
            to_terminal=True,
        )
        try:
            from core.logging import timer

            with timer.timed("Incremental Compilation"):
                patched_graph = adapter.compile_incremental(
                    patched_graph, repository_input
                )
        except Exception as exc:
            raise RepositoryCompilationFailed(
                f"Incremental compilation failed: {exc}",
                details={
                    "repository": request.repository.full_name,
                    "language": language,
                    "sha": head_sha,
                },
            ) from exc

        changed_compile_time = metrics.get(
            "compile_duration", time.perf_counter() - incremental_start
        )
        patch_duration = metrics.get("patch_duration", 0.0)

        return (
            patched_graph,
            changed_fetch_time,
            clone_duration,
            changed_compile_time,
            patch_duration,
            metrics,
        )

    async def _lazy_compile_facts_and_view(
        self, context: PipelineContext, request: AnalysisRequest
    ) -> None:
        """
        Lazy Step 1:
        Does NOT download base ZIP. Initializes view with a metadata tree,
        only indexes changed files from head, and attaches RepositoryResolver.
        """
        import time
        from core.logging import pipeline_logger
        from engine.repository.indexing import RepositoryIndexer
        from engine.repository.store import PersistentFactSink, SQLiteRepositoryStore
        from engine.repository.materialization.request import MaterializationRequest
        from engine.repository.materialization.budget import MaterializationBudget
        from engine.repository.materialization.materializer import RepositoryMaterializer
        from engine.repository.resolver.resolver import RepositoryResolver
        from engine.repository.overlay import RepositoryOverlay, RepositoryView
        from engine.repository.facts import (
            File, FileId, Symbol, SymbolId, Call, Reference, Import,
            TypeRelationship, Endpoint, DatabaseRelationship,
            EventPublication, EventSubscription, TestRelationship
        )

        if self.repository_provider is None:
            raise RepositoryNotInstalled(
                "Repository fact compilation requires a repository provider.",
                details={"repository": request.repository.full_name},
            )

        # 1. Resolve SHAs
        if request.pull_request:
            base_sha = request.pull_request.base_sha
            head_sha = request.pull_request.head_sha
        else:
            base_sha = request.repository.default_branch
            head_sha = request.repository.default_branch

        context.base_sha = base_sha
        context.head_sha = head_sha

        # Timings instrumentation
        repository_metadata_duration = 0.0
        repository_tree_duration = 0.0
        changed_file_acquisition_duration = 0.0
        changed_file_indexing_duration = 0.0
        repository_view_construction_duration = 0.0

        full_name = request.repository.full_name
        provider = getattr(request.repository, "provider", "github") or "github"
        repo_id = (
            f"{provider}/{full_name}"
            if not full_name.startswith(f"{provider}/")
            else full_name
        )

        # Ensure we have base_query (which is SQLiteRepositoryStore)
        actual_repo_id = self.repository_store.create_repository(
            provider, getattr(request.repository, "owner", None) or full_name.split("/")[0],
            getattr(request.repository, "repository", None) or full_name.split("/")[-1]
        )
        actual_version_id = self.repository_store.create_version(
            actual_repo_id, base_sha
        )
        self.repository_store.set_version_context(
            actual_repo_id, actual_version_id
        )
        base_query = self.repository_store
        context.base_query = base_query

        # 2. Fetch base commit metadata
        t0 = time.perf_counter()
        commit_meta = await self.repository_provider.get_commit(request.repository.full_name, base_sha)
        repository_metadata_duration += (time.perf_counter() - t0) * 1000.0

        # 3. Fetch base repository tree metadata
        t1 = time.perf_counter()
        tree_entries = await self.repository_provider.get_tree(request.repository.full_name, base_sha)
        repository_tree_duration += (time.perf_counter() - t1) * 1000.0

        # Record tree metadata in the store
        tree_entries_dicts = [
            {
                "path": entry.path,
                "type": entry.type,
                "blob_sha": entry.sha,
                "size": entry.size or 0
            }
            for entry in tree_entries
        ]
        self.repository_store.record_tree(actual_repo_id, base_sha, tree_entries_dicts)

        # Record repository size (denominator for materialization ratio)
        num_known_files = sum(1 for e in tree_entries if e.type == "blob")
        num_known_bytes = sum(e.size or 0 for e in tree_entries if e.type == "blob")
        context.repository_materialization.set_repository_size(
            files=num_known_files,
            bytes=num_known_bytes,
        )

        # Detect language from tree paths
        if context.language is None:
            detector = LanguageDetector(self.language_registry)
            file_contexts = [
                FileContext(path=entry.path, source="", ast=None, language="")
                for entry in tree_entries if entry.type == "blob"
            ]
            if file_contexts:
                try:
                    spec = detector.detect(file_contexts)
                    language = spec.id
                except Exception:
                    language = "python"
            else:
                language = "python"
            context.language = language
            context.adapter = language
        else:
            language = context.language

        # 4. Fetch PR diff / changed paths
        if context.diff_data is None:
            if request.has_diff:
                context.diff_data = self._diff_snapshot_to_dict(request.diff)
            elif self.repository_provider:
                await self._fetch_diff(context, request)

        # Collect changed paths (ignoring deleted files for head materialization)
        changed_paths = []
        base_tree_paths = {e.path for e in tree_entries if e.type == "blob"}
        
        # 4b. Fetch head tree metadata (so materializer has head expected blob_shas and sizes)
        t_head_start = time.perf_counter()
        head_tree_entries = await self.repository_provider.get_tree(request.repository.full_name, head_sha)
        repository_tree_duration += (time.perf_counter() - t_head_start) * 1000.0
        
        head_tree_entries_dicts = [
            {
                "path": entry.path,
                "type": entry.type,
                "blob_sha": entry.sha,
                "size": entry.size or 0
            }
            for entry in head_tree_entries
        ]
        self.repository_store.record_tree(actual_repo_id, head_sha, head_tree_entries_dicts)
        head_tree_by_path = {e.path: e for e in head_tree_entries}

        if context.diff_data and "files" in context.diff_data:
            for file_info in context.diff_data["files"]:
                change_type = file_info.get("change_type")
                if change_type is None:
                    file_path = file_info["file_path"]
                    if file_path in base_tree_paths:
                        if file_path not in head_tree_by_path:
                            change_type = "deleted"
                        else:
                            change_type = "modified"
                    else:
                        change_type = "added"
                
                if change_type != "deleted":
                    changed_paths.append(file_info["file_path"])

        # Reserve base FileIds for changed files in database
        if hasattr(self.repository_store, "conn"):
            conn = self.repository_store.conn
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(MAX(id), 0) as max_id FROM files WHERE repository_id = ? AND version_id = ?",
                (actual_repo_id, actual_version_id),
            )
            row = cur.fetchone()
            next_id = row["max_id"] + 1 if row else 1
            
            for file_info in context.diff_data.get("files", []):
                file_path = file_info["file_path"]
                cur.execute(
                    "SELECT id FROM files WHERE repository_id = ? AND version_id = ? AND path = ?",
                    (actual_repo_id, actual_version_id, file_path),
                )
                if not cur.fetchone():
                    if file_path in base_tree_paths:
                        cur.execute(
                            "INSERT INTO files (repository_id, version_id, id, path, language, state) VALUES (?, ?, ?, ?, ?, ?)",
                            (actual_repo_id, actual_version_id, next_id, file_path, language, "active"),
                        )
                        next_id += 1
            conn.commit()

        # 5. Fetch changed file blobs & index them
        # Sync indexer and materializer
        sink = PersistentFactSink(
            self.repository_store, actual_repo_id, actual_version_id
        )
        indexer = RepositoryIndexer(sink)

        budget = MaterializationBudget(
            max_files=5000,
            max_bytes=500 * 1024 * 1024,
            max_remote_requests=500
        )
        materializer = RepositoryMaterializer(
            source=self.repository_provider,
            store=self.repository_store,
            indexer=indexer,
            budget=budget,
            metrics=context.repository_materialization,
        )

        acq_before = context.repository_materialization.repository_acquisition_ms
        idx_before = context.repository_materialization.repository_indexing_ms

        mat_res = None
        if changed_paths:
            mat_req = MaterializationRequest(
                repository_id=actual_repo_id,
                commit_sha=head_sha,
                paths=tuple(changed_paths),
                reason="pr_changed_files",
            )
            mat_res = await materializer.materialize(mat_req)

        changed_file_acquisition_duration += (context.repository_materialization.repository_acquisition_ms - acq_before)
        changed_file_indexing_duration += (context.repository_materialization.repository_indexing_ms - idx_before)

        # 6. Construct RepositoryOverlay
        t_view_start = time.perf_counter()
        added_files = {}
        removed_files = set()
        modified_files = set()

        if context.diff_data:
            for file_info in context.diff_data.get("files", []):
                file_path = file_info["file_path"]
                change_type = file_info.get("change_type")

                base_file = base_query.get_file(file_path)

                if change_type is None:
                    if file_path in base_tree_paths:
                        if file_path not in head_tree_by_path:
                            change_type = "deleted"
                        else:
                            change_type = "modified"
                    else:
                        change_type = "added"

                if change_type == "added":
                    file_id = indexer.get_or_create_file_id(file_path)
                    added_files[file_id] = File(
                        id=file_id, path=file_path, language=language
                    )
                elif change_type == "deleted":
                    if base_file is not None:
                        removed_files.add(base_file.id)
                elif change_type == "modified":
                    if base_file is not None:
                        removed_files.add(base_file.id)
                        modified_files.add(base_file.id)
                        file_id = base_file.id
                    else:
                        file_id = indexer.get_or_create_file_id(file_path)
                    added_files[file_id] = File(
                        id=file_id, path=file_path, language=language
                    )

        removed_symbols = set()
        for rf_id in removed_files:
            for s in base_query.get_symbols_in_file(rf_id):
                removed_symbols.add(s.id)

        # Query all facts for the head version from SQL
        cur = self.repository_store.conn.cursor()
        head_version_id = f"{actual_repo_id}@{head_sha}"
        
        # 1. added_symbols
        cur.execute(
            "SELECT id, name, file_id, kind, language, start_line, end_line, visibility, parent_symbol_id "
            "FROM symbols WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_symbols = {}
        for row in cur.fetchall():
            sym = Symbol(
                id=SymbolId(row["id"]),
                name=row["name"],
                file_id=FileId(row["file_id"]),
                kind=row["kind"],
                language=row["language"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                visibility=row["visibility"],
                parent_symbol_id=SymbolId(row["parent_symbol_id"]) if row["parent_symbol_id"] is not None else None,
            )
            added_symbols[sym.id] = sym
            
        # 2. added_calls
        cur.execute(
            "SELECT caller_id, callee_id, call_type FROM calls WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_calls = set()
        for row in cur.fetchall():
            added_calls.add(Call(
                caller_id=SymbolId(row["caller_id"]),
                callee_id=SymbolId(row["callee_id"]),
                call_type=row["call_type"],
            ))
            
        # 3. added_references
        cur.execute(
            "SELECT source_id, target_id, relation_type FROM \"references\" WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_references = set()
        for row in cur.fetchall():
            added_references.add(Reference(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relation_type=row["relation_type"],
            ))
            
        # 4. added_imports
        cur.execute(
            "SELECT source_file_id, target_file_id, module, imported_name, import_type "
            "FROM imports WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_imports = set()
        for row in cur.fetchall():
            added_imports.add(Import(
                source_file_id=FileId(row["source_file_id"]),
                target_file_id=FileId(row["target_file_id"]) if row["target_file_id"] is not None else None,
                module=row["module"],
                imported_name=row["imported_name"],
                import_type=row["import_type"],
            ))
            
        # 5. added_type_relationships
        cur.execute(
            "SELECT source_id, target_id, relationship_type FROM type_relationships WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_type_relationships = set()
        for row in cur.fetchall():
            added_type_relationships.add(TypeRelationship(
                source_id=SymbolId(row["source_id"]),
                target_id=SymbolId(row["target_id"]),
                relationship_type=row["relationship_type"],
            ))
            
        # 6. added_endpoints
        cur.execute(
            "SELECT id, symbol_id, method, path, framework FROM endpoints WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_endpoints = set()
        for row in cur.fetchall():
            added_endpoints.add(Endpoint(
                id=row["id"],
                symbol_id=SymbolId(row["symbol_id"]),
                method=row["method"],
                path=row["path"],
                framework=row["framework"],
            ))
            
        # 7. added_database_relationships
        cur.execute(
            "SELECT symbol_id, resource_id, relationship_type FROM database_relationships WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_database_relationships = set()
        for row in cur.fetchall():
            added_database_relationships.add(DatabaseRelationship(
                symbol_id=SymbolId(row["symbol_id"]),
                resource_id=row["resource_id"],
                relationship_type=row["relationship_type"],
            ))
            
        # 8. added_event_publications
        cur.execute(
            "SELECT symbol_id, event_id, publication_type FROM event_publications WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_event_publications = set()
        for row in cur.fetchall():
            added_event_publications.add(EventPublication(
                symbol_id=SymbolId(row["symbol_id"]),
                event_id=row["event_id"],
                publication_type=row["publication_type"],
            ))
            
        # 9. added_event_subscriptions
        cur.execute(
            "SELECT symbol_id, event_id, subscription_type FROM event_subscriptions WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_event_subscriptions = set()
        for row in cur.fetchall():
            added_event_subscriptions.add(EventSubscription(
                symbol_id=SymbolId(row["symbol_id"]),
                event_id=row["event_id"],
                subscription_type=row["subscription_type"],
            ))
            
        # 10. added_test_relationships
        cur.execute(
            "SELECT test_symbol_id, target_symbol_id, relationship_type FROM test_relationships WHERE repository_id = ? AND version_id = ?",
            (actual_repo_id, head_version_id),
        )
        added_test_relationships = set()
        for row in cur.fetchall():
            added_test_relationships.add(TestRelationship(
                test_symbol_id=SymbolId(row["test_symbol_id"]),
                target_symbol_id=SymbolId(row["target_symbol_id"]),
                relationship_type=row["relationship_type"],
            ))

        overlay = RepositoryOverlay(
            added_files=added_files,
            removed_files=removed_files,
            modified_files=modified_files,
            added_symbols=added_symbols,
            removed_symbols=removed_symbols,
            added_calls=added_calls,
            added_references=added_references,
            added_imports=added_imports,
            added_type_relationships=added_type_relationships,
            added_endpoints=added_endpoints,
            added_database_relationships=added_database_relationships,
            added_event_publications=added_event_publications,
            added_event_subscriptions=added_event_subscriptions,
            added_test_relationships=added_test_relationships,
        )

        # 7. Construct RepositoryResolver
        # We need a new materializer instance for the base SHA since resolver materializes base files
        base_sink = PersistentFactSink(
            self.repository_store, actual_repo_id, actual_version_id
        )
        base_indexer = RepositoryIndexer(base_sink)
        base_materializer = RepositoryMaterializer(
            source=self.repository_provider,
            store=self.repository_store,
            indexer=base_indexer,
            budget=budget,
            metrics=context.repository_materialization,
        )

        resolver = RepositoryResolver(
            store=self.repository_store,
            source=self.repository_provider,
            materializer=base_materializer,
            planner=None,
            tree_metadata=tree_entries_dicts,
            base_commit=base_sha,
            budget=budget,
        )
        if hasattr(resolver.planner, "set_symbol_fqn_map"):
            resolver.planner.set_symbol_fqn_map(indexer._symbol_fqn_map)
        
        # Link resolver to base view for nested lazy queries
        base_query.resolver = resolver

        # 8. Construct RepositoryView
        context.repository_view = RepositoryView(
            base=base_query,
            overlay=overlay,
            resolver=resolver,
            repository_id=actual_repo_id,
            commit_sha=base_sha,
            symbol_fqn_map=indexer._symbol_fqn_map,
        )

        # Restore version context to base commit
        self.repository_store.set_version_context(
            actual_repo_id, actual_version_id
        )

        repository_view_construction_duration += (time.perf_counter() - t_view_start) * 1000.0

        # Print/log timings & counts as per point 21
        initial_changed_files = len(changed_paths)
        initial_materialized_files = len(mat_res.materialized_paths) if mat_res else 0
        initial_ratio = 0.0
        if num_known_files > 0:
            initial_ratio = (initial_changed_files / num_known_files) * 100.0

        print(f"[repository]\ntree_paths={num_known_files}\n")
        print(f"[repository]\ninitial_changed_files={initial_changed_files}\n")
        print(f"[repository]\ninitial_materialized_files={initial_materialized_files}\n")
        print(f"[repository]\ninitial_materialization_ratio={initial_ratio:.4f}%\n")

        pipeline_logger.log_pipeline(
            f"[repository] repository_metadata_duration={repository_metadata_duration:.2f}ms\n"
            f"[repository] repository_tree_duration={repository_tree_duration:.2f}ms\n"
            f"[repository] changed_file_acquisition_duration={changed_file_acquisition_duration:.2f}ms\n"
            f"[repository] changed_file_indexing_duration={changed_file_indexing_duration:.2f}ms\n"
            f"[repository] repository_view_construction_duration={repository_view_construction_duration:.2f}ms",
            to_terminal=True,
        )

        context.mark_repository_compiled()

    async def _compile_facts_and_view(
        self, context: PipelineContext, request: AnalysisRequest
    ) -> None:
        """
        Compile base facts from persistent store and PR overlay from diff.
        Does NOT construct RepositoryGraph or RepositoryModel.
        """
        from core.config import get_compiler_settings
        if get_compiler_settings().ENABLE_LAZY_REPOSITORY_RESOLUTION:
            is_mock_provider = False
            try:
                from unittest.mock import Mock
                if isinstance(self.repository_provider, Mock):
                    is_mock_provider = True
            except ImportError:
                pass

            if (
                self.repository_provider is not None
                and not is_mock_provider
                and hasattr(self.repository_provider, "get_commit")
                and hasattr(self.repository_provider, "get_tree")
            ):
                try:
                    await self._lazy_compile_facts_and_view(context, request)
                    return
                except Exception as exc:
                    print(f"[pipeline] Lazy repository compilation failed: {exc}. Falling back to eager compilation.")
            else:
                print("[pipeline] Repository provider does not support lazy metadata APIs or is a mock. Falling back to eager compilation.")

        if self.repository_provider is None:
            raise RepositoryNotInstalled(
                "Repository fact compilation requires a repository provider. "
                "No repository provider configured.",
                details={"repository": request.repository.full_name},
            )

        # Determine which SHAs to compile
        if request.pull_request:
            base_sha = request.pull_request.base_sha
            head_sha = request.pull_request.head_sha
        else:
            base_sha = request.repository.default_branch
            head_sha = request.repository.default_branch

        context.base_sha = base_sha
        context.head_sha = head_sha

        from core.logging import pipeline_logger

        with timer.timed(
            "Repository Compilation",
            metadata={"base_sha": base_sha, "head_sha": head_sha},
        ):
            start_time = time.perf_counter()
            full_name = request.repository.full_name
            provider = getattr(request.repository, "provider", "github") or "github"
            repo_id = (
                f"{provider}/{full_name}"
                if not full_name.startswith(f"{provider}/")
                else full_name
            )

            # Try provider/owner/repo first, then owner/repo
            possible_repo_ids = [repo_id, full_name]

            # Ensure diff is available
            if context.diff_data is None:
                if request.has_diff:
                    context.diff_data = self._diff_snapshot_to_dict(request.diff)
                elif self.repository_provider:
                    await self._fetch_diff(context, request)

            # 1. Resolve Base Query Interface from Persistent Store
            base_query: RepositoryQuery | None = None
            base_cached = False
            version_id = None

            if self.repository_store is not None and isinstance(
                self.repository_store, RepositoryStore
            ):
                for candidate_id in possible_repo_ids:
                    candidate_version = f"{candidate_id}@{base_sha}"
                    try:
                        self.repository_store.set_version_context(
                            candidate_id, candidate_version
                        )
                        base_query = self.repository_store
                        base_cached = True
                        version_id = candidate_version
                        print(
                            f"[pipeline] Loaded base facts for {candidate_version} from RepositoryStore"
                        )
                        break
                    except Exception:
                        pass

            # If not in persistent store, fetch on-demand or use base snapshot from context
            if base_query is None:
                snapshot = None
                if context.base_repository_snapshot is not None:
                    snapshot = context.base_repository_snapshot
                elif self.repository_provider is not None:
                    try:
                        print(
                            f"[pipeline] Base facts for {repo_id}@{base_sha} not found in store. Fetching repository on-demand..."
                        )
                        acq_start = time.perf_counter()
                        snapshot = (
                            await self.repository_provider.fetch_repository_at_sha(
                                request.repository, base_sha
                            )
                        )
                        acq_duration = (time.perf_counter() - acq_start) * 1000
                        context.repository_materialization.repository_acquisition_ms += acq_duration
                    except Exception as exc:
                        print(
                            f"[pipeline] Failed to fetch repository at base SHA {base_sha}: {exc}"
                        )
                        snapshot = None

                if snapshot is not None:
                    context.repository_materialization.set_repository_size(
                        files=len(snapshot.files),
                        bytes=sum(
                            len(content.encode("utf-8"))
                            for content in snapshot.files.values()
                        ),
                    )
                    if context.language is None:
                        detector = LanguageDetector(self.language_registry)
                        file_contexts = [
                            FileContext(path=path, source=content, ast=None, language="")
                            for path, content in snapshot.files.items()
                        ]
                        spec = detector.detect(file_contexts)
                        language = spec.id
                        context.language = language
                        context.adapter = language
                    else:
                        language = context.language
                    plugin = self.language_registry.get(language)
                    adapter = plugin.create_adapter()

                    if self.repository_store is not None and isinstance(
                        self.repository_store, SQLiteRepositoryStore
                    ):
                        try:
                            owner = getattr(request.repository, "owner", None)
                            repo_name_only = getattr(
                                request.repository, "repository", None
                            )
                            if not owner or not repo_name_only:
                                parts = full_name.split("/", 1)
                                owner = parts[0] if len(parts) > 1 else ""
                                repo_name_only = (
                                    parts[1] if len(parts) > 1 else parts[0]
                                )

                            actual_repo_id = self.repository_store.create_repository(
                                provider, owner, repo_name_only
                            )
                            actual_version_id = self.repository_store.create_version(
                                actual_repo_id, base_sha
                            )
                            self.repository_store.set_version_context(
                                actual_repo_id, actual_version_id
                            )

                            sink = PersistentFactSink(
                                self.repository_store, actual_repo_id, actual_version_id
                            )
                            indexer = RepositoryIndexer(sink)
                            idx_start = time.perf_counter()
                            indexer.index_repository(
                                {"files": snapshot.files, "language": language}, adapter,
                                metrics=context.repository_materialization
                            )
                            idx_duration = (time.perf_counter() - idx_start) * 1000
                            context.repository_materialization.repository_indexing_ms += idx_duration
                            sink.flush()

                            base_query = self.repository_store
                            base_cached = True
                            version_id = actual_version_id
                            print(
                                f"[pipeline] Successfully indexed base facts for {actual_version_id} into RepositoryStore"
                            )
                        except Exception as exc:
                            print(
                                f"[pipeline] Failed to persist facts to RepositoryStore: {exc}, falling back to InMemoryRepository"
                            )
                            base_sink = InMemoryFactSink()
                            base_indexer = RepositoryIndexer(base_sink)
                            idx_start = time.perf_counter()
                            base_indexer.index_repository(
                                {"files": snapshot.files, "language": language}, adapter,
                                metrics=context.repository_materialization
                            )
                            idx_duration = (time.perf_counter() - idx_start) * 1000
                            context.repository_materialization.repository_indexing_ms += idx_duration
                            base_facts = base_sink.build_facts()
                            base_query = InMemoryRepository(base_facts)
                    else:
                        base_sink = InMemoryFactSink()
                        base_indexer = RepositoryIndexer(base_sink)
                        idx_start = time.perf_counter()
                        base_indexer.index_repository(
                            {"files": snapshot.files, "language": language}, adapter,
                            metrics=context.repository_materialization
                        )
                        idx_duration = (time.perf_counter() - idx_start) * 1000
                        context.repository_materialization.repository_indexing_ms += idx_duration
                        base_facts = base_sink.build_facts()
                        base_query = InMemoryRepository(base_facts)
                else:
                    missing_version = version_id or f"{repo_id}@{base_sha}"
                    raise RepositoryCompilationFailed(
                        f"Base repository facts for version {missing_version} not found in persistent store and could not be fetched on-demand.",
                        details={"repository": repo_id, "sha": base_sha},
                    )

            context.base_query = base_query
            language = context.language
            if language is None and base_query is not None:
                if hasattr(base_query, "conn"):
                    try:
                        cur = base_query.conn.cursor()
                        repo_id, version_id = base_query._get_context()
                        cur.execute(
                            "SELECT language FROM files WHERE repository_id = ? AND version_id = ? LIMIT 1",
                            (repo_id, version_id),
                        )
                        row = cur.fetchone()
                        if row:
                            language = row["language"]
                    except Exception:
                        pass
                elif hasattr(base_query, "_facts"):
                    try:
                        files = base_query._facts.files
                        if files:
                            language = files[0].language
                    except Exception:
                        pass

            language = language or "python"
            context.language = language
            context.adapter = language

            # 2. Fetch changed files from diff only
            changed_files_dict = {}
            if (
                request.pull_request
                and context.diff_data
                and "files" in context.diff_data
            ):

                async def fetch_one(file_path: str):
                    try:
                        if self.repository_provider is None:
                            return file_path, None
                        content = await self.repository_provider.fetch_file(
                            request.repository, file_path, head_sha
                        )
                        return file_path, content
                    except Exception as exc:
                        print(f"[pipeline] File {file_path} not found at head: {exc}")
                        return file_path, None

                acq_start = time.perf_counter()
                tasks = [
                    fetch_one(file_info["file_path"])
                    for file_info in context.diff_data["files"]
                ]
                results = await asyncio.gather(*tasks)
                acq_duration = (time.perf_counter() - acq_start) * 1000
                context.repository_materialization.repository_acquisition_ms += acq_duration
                changed_files_dict = dict(results)

            # 3. Index ONLY changed files
            plugin = self.language_registry.get(language)
            adapter = plugin.create_adapter()
            head_sink = InMemoryFactSink()
            head_indexer = RepositoryIndexer(head_sink)

            # Sync head_indexer with base_query to ensure stable file and symbol IDs
            from engine.repository.facts import FileId, SymbolId
            from engine.repository.indexing.indexer import build_symbol_fqn
            if hasattr(base_query, "conn"):
                try:
                    cur = base_query.conn.cursor()
                    repo_id, version_id = base_query._get_context()

                    # Load files
                    cur.execute(
                        "SELECT id, path FROM files WHERE repository_id = ? AND version_id = ?",
                        (repo_id, version_id),
                    )
                    for row in cur.fetchall():
                        f_id = row["id"]
                        f_path = row["path"]
                        head_indexer._file_id_map[f_path] = FileId(f_id)
                        if f_id >= head_indexer._next_file_id:
                            head_indexer._next_file_id = f_id + 1

                    # Load symbols and reconstruct FQNs
                    cur.execute(
                        "SELECT s.id, s.name, s.kind, s.language, s.parent_symbol_id, f.path as file_path "
                        "FROM symbols s JOIN files f ON s.repository_id = f.repository_id AND s.version_id = f.version_id AND s.file_id = f.id "
                        "WHERE s.repository_id = ? AND s.version_id = ?",
                        (repo_id, version_id),
                    )
                    rows = cur.fetchall()
                    parent_map = {row["id"]: row["name"] for row in rows}

                    for row in rows:
                        sym_id = row["id"]
                        sym_name = row["name"]
                        sym_kind = row["kind"]
                        sym_lang = row["language"]
                        file_path = row["file_path"]
                        parent_id = row["parent_symbol_id"]

                        parent_name = parent_map.get(parent_id, "") if parent_id else ""
                        fqn = build_symbol_fqn(sym_lang, file_path, sym_name, sym_kind, parent_name)

                        head_indexer._symbol_id_map[fqn] = SymbolId(sym_id)
                        head_indexer._symbol_fqn_map[SymbolId(sym_id)] = fqn
                        if sym_id >= head_indexer._next_symbol_id:
                            head_indexer._next_symbol_id = sym_id + 1
                except Exception as e:
                    print(f"[pipeline] Warning: Failed to populate head_indexer from base_query: {e}")

            files_to_index = {
                f: c for f, c in changed_files_dict.items() if c is not None
            }
            head_idx_start = time.perf_counter()
            head_indexer.index_repository(
                {"files": files_to_index, "language": language}, adapter,
                metrics=context.repository_materialization
            )
            head_idx_duration = (time.perf_counter() - head_idx_start) * 1000
            context.repository_materialization.repository_indexing_ms += head_idx_duration
            head_facts = head_sink.build_facts()

            # 4. Construct RepositoryOverlay
            added_files = {}
            removed_files = set()
            modified_files = set()

            if context.diff_data:
                for file_info in context.diff_data.get("files", []):
                    file_path = file_info["file_path"]
                    change_type = file_info.get("change_type")

                    base_file = base_query.get_file(file_path)

                    if change_type is None:
                        # Infer change_type based on presence in base and head
                        head_content = changed_files_dict.get(file_path)
                        if base_file is not None:
                            if head_content is None:
                                change_type = "deleted"
                            else:
                                change_type = "modified"
                        else:
                            change_type = "added"

                    if change_type == "added":
                        file_id = head_indexer.get_or_create_file_id(file_path)
                        added_files[file_id] = File(
                            id=file_id, path=file_path, language=language
                        )
                    elif change_type == "deleted":
                        if base_file is not None:
                            removed_files.add(base_file.id)
                    elif change_type == "modified":
                        if base_file is not None:
                            removed_files.add(base_file.id)
                            modified_files.add(base_file.id)
                            file_id = base_file.id
                        else:
                            file_id = head_indexer.get_or_create_file_id(file_path)
                        added_files[file_id] = File(
                            id=file_id, path=file_path, language=language
                        )

            removed_symbols = set()
            for rf_id in removed_files:
                for s in base_query.get_symbols_in_file(rf_id):
                    removed_symbols.add(s.id)

            overlay = RepositoryOverlay(
                added_files=added_files,
                removed_files=removed_files,
                modified_files=modified_files,
                added_symbols={s.id: s for s in head_facts.symbols},
                removed_symbols=removed_symbols,
                added_calls=set(head_facts.calls),
                added_references=set(head_facts.references),
                added_imports=set(head_facts.imports),
                added_type_relationships=set(head_facts.type_relationships),
                added_endpoints=set(head_facts.endpoints),
                added_database_relationships=set(head_facts.database_relationships),
                added_event_publications=set(head_facts.event_publications),
                added_event_subscriptions=set(head_facts.event_subscriptions),
                added_test_relationships=set(head_facts.test_relationships),
            )

            context.repository_view = RepositoryView(
                base=base_query,
                overlay=overlay,
                repository_id=repo_id,
                commit_sha=base_sha,
                symbol_fqn_map=head_indexer._symbol_fqn_map,
            )
            compile_duration = time.perf_counter() - start_time

        context.mark_repository_compiled()
        pipeline_logger.log_pipeline(
            f"[Pipeline] Fact-based repository compilation complete in {compile_duration:.2f}s",
            to_terminal=True,
        )
        pipeline_logger.log_pipeline(
            f"  ✓ Persistent facts loaded ({'cached' if base_cached else 'indexed'})",
            to_terminal=True,
        )
        pipeline_logger.log_pipeline(
            f"  ✓ PR overlay constructed ({len(changed_files_dict)} changed files)",
            to_terminal=True,
        )

    async def _compile_both_repository_models(
        self, context: PipelineContext, request: AnalysisRequest
    ) -> None:
        """Deprecated alias that delegates to _compile_facts_and_view."""
        await self._compile_facts_and_view(context, request)

        changed_fetch_str = f"{changed_fetch_time:.1f}s"
        pipeline_logger.log_pipeline(
            f"  ✓ Fetch changed files ({changed_fetch_str})", to_terminal=True
        )

        changed_compile_str = f"{changed_compile_time:.1f}s"
        pipeline_logger.log_pipeline(
            f"  ✓ Compile changed files ({changed_compile_str})", to_terminal=True
        )

        patch_duration_str = f"{patch_duration:.1f}s"
        pipeline_logger.log_pipeline(
            f"  ✓ Patch repository graph ({patch_duration_str})", to_terminal=True
        )

        export_duration_str = f"{head_export_duration:.1f}s"
        pipeline_logger.log_pipeline(
            f"  ✓ Export RepositoryModel ({export_duration_str})", to_terminal=True
        )

        # Telemetry detail logging
        changed_files_compiled = metrics.get("changed_files_compiled", 0)
        files_skipped = metrics.get("files_skipped", len(base_graph.files))
        symbols_replaced = metrics.get("symbols_replaced", 0)
        symbols_inserted = metrics.get("symbols_inserted", 0)
        symbols_removed = metrics.get("symbols_removed", 0)
        edges_updated = metrics.get("edges_updated", 0)

        pipeline_logger.log_pipeline("", to_terminal=True)
        pipeline_logger.log_pipeline(
            f"  Base files compiled: {base_files_compiled}", to_terminal=True
        )
        pipeline_logger.log_pipeline(
            f"  Changed files compiled: {changed_files_compiled}", to_terminal=True
        )
        pipeline_logger.log_pipeline(
            f"  Files skipped: {files_skipped}", to_terminal=True
        )
        pipeline_logger.log_pipeline(
            f"  Symbols replaced: {symbols_replaced}", to_terminal=True
        )
        pipeline_logger.log_pipeline(
            f"  Symbols inserted: {symbols_inserted}", to_terminal=True
        )
        pipeline_logger.log_pipeline(
            f"  Symbols removed: {symbols_removed}", to_terminal=True
        )
        pipeline_logger.log_pipeline(
            f"  Edges updated: {edges_updated}", to_terminal=True
        )
        pipeline_logger.log_pipeline(
            f"  Patch duration: {patch_duration:.3f}s", to_terminal=True
        )
        pipeline_logger.log_pipeline(
            f"  Export duration: {head_export_duration:.3f}s", to_terminal=True
        )

    async def _fetch_diff(
        self, context: PipelineContext, request: AnalysisRequest
    ) -> None:
        """
        Fetch diff for the repository.

        Args:
            context: Pipeline context
            request: Analysis request

        Raises:
            DiffFetchFailed: If diff fetching fails
        """
        if self.repository_provider is None:
            raise DiffFetchFailed(
                "Diff fetching requires a repository provider. "
                "No repository provider configured.",
                details={"repository": context.repository},
            )

        if not request.pull_request:
            raise DiffFetchFailed(
                "Diff fetching requires a pull request",
                details={"repository": context.repository},
            )

        diff = await self.repository_provider.fetch_diff(
            request.repository,
            request.pull_request.base_sha,
            request.pull_request.head_sha,
        )

        # Convert DiffSnapshot to dict format expected by compilers
        context.diff_data = self._diff_snapshot_to_dict(diff)

    def _diff_snapshot_to_dict(self, diff: Any) -> dict[str, Any]:
        """Convert DiffSnapshot to dictionary format.

        Args:
            diff: DiffSnapshot object

        Returns:
            Dictionary format for compilers
        """
        return {
            "files": [
                {
                    "file_path": f.file_path,
                    "added_lines": list(f.added_lines),
                    "removed_lines": list(f.removed_lines),
                    "hunks": [
                        {
                            "file_path": h.file_path,
                            "source_start": h.source_start,
                            "source_length": h.source_length,
                            "target_start": h.target_start,
                            "target_length": h.target_length,
                            "added_lines": list(h.added_lines),
                            "removed_lines": list(h.removed_lines),
                            "lines": list(h.lines),
                        }
                        for h in f.hunks
                    ],
                }
                for f in diff.files
            ]
        }

    async def _compile_change(self, context: PipelineContext) -> None:
        """
        Compile change model using RepositoryQuery and RepositoryView.
        """
        if context.repository_view is None and context.base_repository_model is None:
            raise PipelineExecutionError(
                "Repository query interface not available for change compilation",
                details={"repository": context.repository},
            )

        if context.diff_data is None:
            raise InvalidDiff(
                "Diff data not provided",
                details={"repository": context.repository},
            )

        try:
            if context.repository_view is not None:
                base_query = context.base_query or getattr(
                    context.repository_view, "base", None
                )
                if getattr(context.repository_view, "resolver", None) is not None:
                    # Wrap base_query in a RepositoryView with empty overlay to propagate lazy resolution
                    base_query = RepositoryView(
                        base=base_query,
                        overlay=RepositoryOverlay(),
                        resolver=context.repository_view.resolver,
                        repository_id=context.repository_view.repository_id,
                        commit_sha=context.repository_view.commit_sha,
                    )
                head_query = context.repository_view
                context.change_facts = self._change_compiler.compile(
                    diff=context.diff_data,
                    repository=base_query,
                    head_repository=head_query,
                )
                context.change_model = context.change_facts
            else:
                comparison = RepositoryComparison(
                    base_model=context.base_repository_model,
                    head_model=context.head_repository_model,
                    diff=context.diff_data,
                    base_sha=context.base_sha or "",
                    head_sha=context.head_sha or "",
                )
                context.change_model = self._change_compiler.compile(
                    comparison=comparison
                )
            context.mark_change_compiled()
            # Diagnostics
            cf = context.change_facts or context.change_model
            if cf is not None:
                n_sym = len(getattr(cf, "changed_symbols", ())) or (
                    len(getattr(cf, "added_symbols", ()))
                    + len(getattr(cf, "removed_symbols", ()))
                    + len(getattr(cf, "modified_symbols", ()))
                )
                n_files = getattr(cf, "files_changed", 0)
                print(f"[change] changed_symbols={n_sym} files={n_files}")
        except Exception as exc:
            raise PipelineExecutionError(
                f"Change compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    def _get_repository_capabilities(self, context: PipelineContext) -> Any:
        """
        Compute the union of capabilities for all languages present in this repository version.
        """
        detected_languages = set()

        # 1. Check if we have snapshot files (on-demand indexing)
        snapshot = context.base_repository_snapshot
        if snapshot and snapshot.files:
            for file_path in snapshot.files:
                import os
                filename = os.path.basename(file_path)
                plugin = self.language_registry.find_by_filename(filename)
                if not plugin:
                    _, ext = os.path.splitext(file_path)
                    plugin = self.language_registry.find_by_extension(ext)
                if plugin:
                    detected_languages.add(plugin.spec.id)

        # 2. Check if we have a base query (SQLite/InMemory) with files
        base_query = context.base_query
        if base_query is not None:
            if hasattr(base_query, "conn"):
                try:
                    cur = base_query.conn.cursor()
                    repo_id, version_id = base_query._get_context()
                    cur.execute(
                        "SELECT DISTINCT language FROM files WHERE repository_id = ? AND version_id = ?",
                        (repo_id, version_id),
                    )
                    for row in cur.fetchall():
                        detected_languages.add(row["language"])
                except Exception:
                    pass
            elif hasattr(base_query, "_facts"):
                try:
                    for f in base_query._facts.files:
                        detected_languages.add(f.language)
                except Exception:
                    pass

        # 3. Fallback to context.language if nothing detected yet
        if not detected_languages and context.language:
            detected_languages.add(context.language)

        # 4. If still empty, default to python
        if not detected_languages:
            detected_languages.add("python")

        # 5. Merge capabilities
        merged = {
            "symbols": False,
            "imports": False,
            "calls": False,
            "types": False,
            "entrypoints": False,
            "events": False,
            "persistence": False,
            "tests": False,
        }
        for lang in detected_languages:
            try:
                spec = self.language_registry.get(lang).spec
                for key in merged:
                    if getattr(spec.capabilities, key, False):
                        merged[key] = True
            except Exception:
                pass

        from engine.language.base.capabilities import LanguageCapabilities
        return LanguageCapabilities(**merged)

    async def _compile_behavior(self, context: PipelineContext) -> None:
        """
        Compile behavior model.
        """
        change_input = context.change_facts or context.change_model
        if change_input is None:
            raise PipelineExecutionError(
                "Change model not available",
                details={"repository": context.repository},
            )

        try:
            query_input = context.repository_view or (
                context.repository_delta.head_model
                if context.repository_delta
                else None
            )
            capabilities = self._get_repository_capabilities(context)
            context.impact_surface = self._behavior_compiler.compile(
                change_model=change_input,
                repository_query=query_input,
                repository_delta=context.repository_delta,
                capabilities=capabilities,
            )
            context.behavior_model = context.impact_surface
            context.mark_behavior_compiled()
            # Diagnostics
            imp = context.impact_surface
            if imp is not None:
                n_syms = len(getattr(imp, "affected_symbols", frozenset()))
                n_eps = len(getattr(imp, "affected_endpoints", frozenset()))
                n_dbs = len(getattr(imp, "affected_databases", frozenset()))
                n_evts = len(getattr(imp, "affected_events", frozenset()))
                print(
                    f"[impact] affected_symbols={n_syms} endpoints={n_eps} databases={n_dbs} events={n_evts}"
                )
        except Exception as exc:
            raise PipelineExecutionError(
                f"Behavior compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    async def _compile_operational(self, context: PipelineContext) -> None:
        """
        Compile operational change model.
        """
        change_input = context.change_facts or context.change_model
        if change_input is None:
            raise PipelineExecutionError(
                "Change model not available",
                details={"repository": context.repository},
            )

        if context.behavior_model is None:
            raise PipelineExecutionError(
                "Behavior model not available",
                details={"repository": context.repository},
            )

        try:
            query_input = context.repository_view or (
                context.repository_delta.head_model
                if context.repository_delta
                else None
            )
            capabilities = self._get_repository_capabilities(context)
            context.ocm = self._operational_compiler.compile(
                repository_delta=context.repository_delta,
                change_model=change_input,
                behavior_model=context.behavior_model,
                repository_query=query_input,
                capabilities=capabilities,
            )
            context.mark_operational_compiled()
            # Diagnostics
            ocm = context.ocm
            if ocm is not None:
                api_m = getattr(ocm, "api", None)
                val_m = getattr(ocm, "validation", None)
                n_rest = len(getattr(api_m, "rest", ())) if api_m else 0
                n_unit = len(getattr(val_m, "unit_tests", ())) if val_m else 0
                n_integ = len(getattr(val_m, "integration_tests", ())) if val_m else 0
                print(
                    f"[operational] api_rest={n_rest} validation_unit={n_unit} validation_integration={n_integ}"
                )
        except Exception as exc:
            raise PipelineExecutionError(
                f"Operational compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    async def _compile_discovery(self, context: PipelineContext) -> None:
        """
        Compile engineering discovery model from the operational model.

        Args:
            context: Pipeline context

        Raises:
            PipelineExecutionError: If compilation fails
        """
        if context.ocm is None:
            raise PipelineExecutionError(
                "Operational model not available for discovery compilation",
                details={"repository": context.repository},
            )

        try:
            context.edm = self._discovery_compiler.from_operational_model(context.ocm)
        except Exception as exc:
            raise PipelineExecutionError(
                f"Engineering discovery compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    async def _compile_discovery_ir(self, context: PipelineContext) -> None:
        """
        Compile discovery IR from the engineering discovery model.

        The Discovery Compiler performs deterministic engineering discovery.
        It produces DiscoveryIR — the canonical intermediate representation
        that the Presentation Compiler consumes.

        Args:
            context: Pipeline context

        Raises:
            PipelineExecutionError: If compilation fails
        """
        if context.edm is None:
            raise PipelineExecutionError(
                "Engineering discovery model not available for discovery IR compilation",
                details={"repository": context.repository},
            )

        try:
            import time

            start = time.time()

            discovery_compiler = DiscoveryCompiler()
            context.discovery_ir = discovery_compiler.compile(context.edm)

            context.discovery_compile_time = time.time() - start
            context.mark_discovery_compiled()
        except Exception as exc:
            raise PipelineExecutionError(
                f"Discovery IR compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    async def _compile_review_context(self, context: PipelineContext) -> None:
        """
        Compile ReviewContext from existing compiler outputs.

        The ReviewContext Compiler selects, normalizes, and organizes
        existing compiler outputs into a stable engineering context.
        It performs no discovery, no graph traversal, no recomputation.

        Args:
            context: Pipeline context

        Raises:
            PipelineExecutionError: If compilation fails
        """
        try:
            import time

            start = time.time()

            context.review_context = self._review_context_compiler.compile(
                change_model=context.change_model,
                behavior_model=context.behavior_model,
                operational_model=context.ocm,
                discovery_model=context.discovery_ir,
            )

            context.presentation_compile_time = time.time() - start
            context.mark_presentation_compiled()
            # Diagnostics
            rc = context.review_context
            if rc is not None:
                n_ep = len(getattr(getattr(rc, "execution", None), "entry_points", ()))
                n_disc = len(getattr(rc, "discoveries", ()))
                n_files = len(getattr(getattr(rc, "change", None), "files", ()))
                print(
                    f"[review] entry_points={n_ep} discoveries={n_disc} change_files={n_files}"
                )

            # Release head repository model reference to free memory
            if context.repository_delta is not None:
                context.repository_delta.release_head_model()
            if context.ocm is not None:
                object.__setattr__(context.ocm, "repository", None)
            if context.edm is not None:
                object.__setattr__(context.edm, "repository", None)
            context.head_repository_model = None
        except Exception as exc:
            raise PipelineExecutionError(
                f"ReviewContext compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    async def _compile_llm_context(self, context: PipelineContext) -> None:
        """
        Compile LLMContext from ReviewContext.

        The LLMContext Compiler produces a lossless, token-efficient
        representation of the ReviewContext by eliminating representational
        redundancy. It performs no semantic interpretation, no AI/LLM usage,
        and no information loss.

        Args:
            context: Pipeline context

        Raises:
            PipelineExecutionError: If compilation fails
        """
        if context.review_context is None:
            raise PipelineExecutionError(
                "ReviewContext not available for LLMContext compilation",
                details={"repository": context.repository},
            )

        try:
            import time

            start = time.time()

            context.llm_context = self._llm_context_compiler.compile(
                context.review_context
            )

            context.llm_compile_time = time.time() - start
            # Diagnostics
            lc = context.llm_context
            if lc is not None:
                n_sym = len(getattr(lc, "sym", ()))
                n_ep = len(getattr(lc, "ep", ()))
                n_cf = len(getattr(lc, "cf", ()))
                n_disc = len(getattr(lc, "disc", ()))
                print(f"[llm] sym={n_sym} ep={n_ep} cf={n_cf} disc={n_disc}")
        except Exception as exc:
            raise PipelineExecutionError(
                f"LLMContext compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    def render_json(self, context: PipelineContext) -> dict[str, Any]:
        """
        Render the pipeline result as JSON.

        Args:
            context: Pipeline context with EDM or OCM

        Returns:
            Dictionary representation

        Raises:
            PipelineExecutionError: If rendering fails
        """
        if context.edm is not None:
            try:
                return self._json_renderer.render(context.edm)
            except Exception as exc:
                raise PipelineExecutionError(
                    f"JSON rendering failed: {exc}",
                    details={"repository": context.repository},
                ) from exc

        if context.ocm is None:
            raise PipelineExecutionError("No model available to render")

        try:
            return self._json_renderer.render(context.ocm)
        except Exception as exc:
            raise PipelineExecutionError(
                f"JSON rendering failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    def render_review_context(self, context: PipelineContext) -> dict[str, Any] | None:
        """
        Render the ReviewContext as a dictionary.

        Args:
            context: Pipeline context with ReviewContext

        Returns:
            Dictionary representation of the ReviewContext, or None if not available

        Raises:
            PipelineExecutionError: If rendering fails
        """
        if context.review_context is None:
            return None

        try:
            rc = context.review_context
            return {
                "change": {
                    "summary": {
                        "classification": rc.change.summary.classification,
                        "scope": rc.change.summary.scope,
                        "file_count": rc.change.summary.file_count,
                        "symbol_count": rc.change.summary.symbol_count,
                        "behavior_count": rc.change.summary.behavior_count,
                    },
                    "files": [
                        {
                            "path": f.path,
                            "language": f.language,
                            "change_type": f.change_type,
                            "changes": [
                                {
                                    "symbol": {
                                        "id": c.symbol.id,
                                        "name": c.symbol.name,
                                        "kind": c.symbol.kind,
                                        "visibility": c.symbol.visibility,
                                        "location": c.symbol.location,
                                    },
                                    "change_type": c.change_type,
                                    "behavior_changes": list(c.behavior_changes),
                                }
                                for c in f.changes
                            ],
                        }
                        for f in rc.change.files
                    ],
                },
                "execution": {
                    "entry_points": [
                        {
                            "endpoint": ep.endpoint,
                            "method": ep.method,
                            "path": ep.path,
                            "execution_chain": [
                                {
                                    "behavior": step.behavior,
                                    "symbol": {
                                        "id": step.symbol.id,
                                        "name": step.symbol.name,
                                        "kind": step.symbol.kind,
                                        "location": step.symbol.location,
                                    },
                                    "kind": step.kind,
                                    "depth": step.depth,
                                    "changed": step.changed,
                                    "shared": step.shared,
                                    "references": list(step.references),
                                }
                                for step in ep.execution_chain
                            ],
                            "terminal": ep.terminal,
                            "max_depth": ep.max_depth,
                            "references": list(ep.references),
                        }
                        for ep in rc.execution.entry_points
                    ],
                    "deepest_execution": {
                        "entry_point": rc.execution.deepest_execution.entry_point,
                        "depth": rc.execution.deepest_execution.depth,
                        "references": list(rc.execution.deepest_execution.references),
                    },
                },
                "discoveries": [
                    {
                        "id": d.id,
                        "kind": d.kind,
                        "statement": d.statement,
                        "reference_count": d.reference_count,
                        "references": [
                            {
                                "id": r.id,
                                "kind": r.kind,
                                "location": r.location,
                                "compiler_artifact": r.compiler_artifact,
                            }
                            for r in d.references
                        ],
                    }
                    for d in rc.discoveries
                ],
            }
        except Exception as exc:
            raise PipelineExecutionError(
                f"ReviewContext rendering failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    def render_github_comment(
        self,
        context: PipelineContext,
        pr_number: int,
    ) -> str:
        """
        Render the pipeline result as a GitHub comment.

        Args:
            context: Pipeline context with EDM or OCM
            pr_number: Pull request number

        Returns:
            Markdown string for GitHub comment

        Raises:
            PipelineExecutionError: If rendering fails
        """
        if context.edm is None and context.ocm is None:
            raise PipelineExecutionError("No model available to render")

        try:
            if self._github_renderer is None:
                self._github_renderer = GitHubRenderer()

            render_context = {
                "repository": context.repository,
                "pr_number": pr_number,
                "base_sha": context.base_sha,
                "head_sha": context.head_sha,
                "language": context.language,
                "total_time": f"{context.total_time:.2f}"
                if context.total_time
                else "N/A",
            }

            # Prefer EDM over OCM
            if context.edm is not None:
                return self._github_renderer.render_artifact(
                    context.edm, render_context
                )
            if context.ocm is not None:
                return self._github_renderer.render(context.ocm, render_context)
            raise PipelineExecutionError("No model available to render")
        except Exception as exc:
            raise PipelineExecutionError(
                f"GitHub rendering failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    async def publish_output(
        self,
        context: PipelineContext,
        destination: dict[str, Any],
    ) -> str | None:
        """
        Publish the analysis result using the output provider.

        Args:
            context: Pipeline context with EDM or OCM
            destination: Destination information

        Returns:
            Published content identifier or None

        Raises:
            PipelineExecutionError: If publishing fails
        """
        if context.edm is None and context.ocm is None:
            raise PipelineExecutionError("No model available to publish")

        if self.output_provider is None:
            raise PipelineExecutionError("No output provider configured")

        try:
            # Prefer EDM over OCM
            model = context.edm if context.edm is not None else context.ocm
            if model is None:
                raise PipelineExecutionError("No model available to publish")
            return await self.output_provider.publish(model, destination)  # type: ignore[arg-type]
        except Exception as exc:
            raise PipelineExecutionError(
                f"Output publishing failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    def build_llm_context(self, context: PipelineContext) -> dict[str, Any]:
        """
        Build LLM context from ReviewContext.

        Args:
            context: Pipeline context with ReviewContext

        Returns:
            LLMContext as a dictionary

        Raises:
            PipelineExecutionError: If context building fails
        """
        if context.review_context is None:
            raise PipelineExecutionError(
                "No ReviewContext available for LLM context building"
            )

        try:
            rc = context.review_context

            return {
                "change": {
                    "summary": {
                        "classification": rc.change.summary.classification,
                        "scope": rc.change.summary.scope,
                        "file_count": rc.change.summary.file_count,
                        "symbol_count": rc.change.summary.symbol_count,
                        "behavior_count": rc.change.summary.behavior_count,
                    },
                    "files": [
                        {
                            "path": f.path,
                            "language": f.language,
                            "change_type": f.change_type,
                            "changes": [
                                {
                                    "symbol": {
                                        "name": c.symbol.name,
                                        "kind": c.symbol.kind,
                                        "visibility": c.symbol.visibility,
                                        "location": c.symbol.location,
                                    },
                                    "change_type": c.change_type,
                                    "behavior_changes": list(c.behavior_changes),
                                }
                                for c in f.changes
                            ],
                        }
                        for f in rc.change.files
                    ],
                },
                "execution": {
                    "entry_points": [
                        {
                            "endpoint": ep.endpoint,
                            "method": ep.method,
                            "path": ep.path,
                            "execution_chain": [
                                {
                                    "behavior": step.behavior,
                                    "symbol": {
                                        "id": step.symbol.id,
                                        "name": step.symbol.name,
                                        "kind": step.symbol.kind,
                                        "location": step.symbol.location,
                                    },
                                    "kind": step.kind,
                                    "depth": step.depth,
                                    "changed": step.changed,
                                    "shared": step.shared,
                                }
                                for step in ep.execution_chain
                            ],
                            "terminal": ep.terminal,
                            "max_depth": ep.max_depth,
                        }
                        for ep in rc.execution.entry_points
                    ],
                    "deepest_execution": {
                        "entry_point": rc.execution.deepest_execution.entry_point,
                        "depth": rc.execution.deepest_execution.depth,
                    },
                },
                "discoveries": [
                    {
                        "id": d.id,
                        "kind": d.kind,
                        "statement": d.statement,
                        "reference_count": d.reference_count,
                        "references": [
                            {
                                "id": r.id,
                                "kind": r.kind,
                                "location": r.location,
                                "compiler_artifact": r.compiler_artifact,
                            }
                            for r in d.references
                        ],
                    }
                    for d in rc.discoveries
                ],
            }
        except Exception as exc:
            raise PipelineExecutionError(
                f"LLM context building failed: {exc}",
                details={"repository": context.repository},
            ) from exc

    def serialize_llm_context(self, context: PipelineContext) -> dict[str, Any] | None:
        """
        Serialize LLMContext to a dictionary for API response.

        The compressed IR is serialized in its native compact format —
        enum IDs, string table indices, and positional tuples are preserved
        to minimize token count. Consumers can reconstruct the original
        ReviewContext or decompress the IR as needed.

        Args:
            context: Pipeline context with LLMContext

        Returns:
            Dictionary representation of LLMContext, or None if not available
        """
        if context.llm_context is None:
            return None

        try:
            llm_ctx = context.llm_context
            strings = list(llm_ctx.st.entries)

            # Resolve DB-backed symbol IDs to full names using RepositoryQuery
            db = context.repository_view or context.base_query
            if db is not None:
                from engine.repository.facts import SymbolId, FileId

                # Identify pure numeric strings as candidate symbol IDs
                candidate_ids = []
                candidate_indices = []
                for idx, s in enumerate(strings):
                    if s and s.isdigit():
                        candidate_ids.append(SymbolId(int(s)))
                        candidate_indices.append(idx)

                if candidate_ids:
                    # Batch fetch symbols
                    symbols = db.get_symbols(candidate_ids)

                    # Recursively resolve parents in batch
                    all_resolved = {sym.id: sym for sym in symbols}
                    curr_symbols = list(symbols)
                    while True:
                        parent_ids_to_fetch = []
                        for sym in curr_symbols:
                            if sym.parent_symbol_id is not None and sym.parent_symbol_id not in all_resolved:
                                parent_ids_to_fetch.append(sym.parent_symbol_id)
                        if not parent_ids_to_fetch:
                            break
                        parents = db.get_symbols(parent_ids_to_fetch)
                        for p in parents:
                            all_resolved[p.id] = p
                        curr_symbols = parents

                    # Batch fetch all required files to get paths
                    file_ids = {sym.file_id for sym in all_resolved.values() if sym.file_id is not None}
                    file_map = {}
                    for fid in file_ids:
                        file_obj = db.get_file(fid)
                        if file_obj:
                            file_map[fid] = file_obj.path

                    # Resolve full qualified names
                    symbol_names = {}
                    for sym in symbols:
                        chain = []
                        curr = sym
                        while curr is not None:
                            chain.append(curr.name)
                            if curr.parent_symbol_id is not None:
                                curr = all_resolved.get(curr.parent_symbol_id)
                            else:
                                curr = None
                        chain.reverse()

                        file_path = file_map.get(sym.file_id, "")
                        if file_path:
                            file_path = file_path.replace('\\', '/')
                            for ext in ['.py', '.java', '.ts', '.tsx', '.js', '.jsx']:
                                if file_path.endswith(ext):
                                    file_path = file_path[:-len(ext)]
                                    break
                            module_parts = [p for p in file_path.split('/') if p]
                            module_name = ".".join(module_parts)
                        else:
                            module_name = ""

                        if module_name:
                            full_name = f"{module_name}.{'.'.join(chain)}"
                        else:
                            full_name = ".".join(chain)

                        symbol_names[sym.id] = full_name

                    # Replace DB IDs in strings list
                    for idx, s in zip(candidate_indices, candidate_ids):
                        if s in symbol_names:
                            strings[idx] = symbol_names[s]

            # Deduplicate the resolved strings and build the remapping table
            new_st_entries = []
            new_st_map = {}
            old_to_new_idx = {}
            for old_idx, s in enumerate(strings):
                if s not in new_st_map:
                    new_idx = len(new_st_entries)
                    new_st_entries.append(s)
                    new_st_map[s] = new_idx
                old_to_new_idx[old_idx] = new_st_map[s]

            # Remap everything referencing st
            result: dict[str, Any] = {
                "st": new_st_entries,
            }

            result["f"] = [[old_to_new_idx.get(path_idx, 0), ct_id] for path_idx, ct_id in llm_ctx.f]
            result["sym"] = [[file_id, old_to_new_idx.get(name_idx, 0), kind_id] for file_id, name_idx, kind_id in llm_ctx.sym]
            result["ep"] = [[method_id, old_to_new_idx.get(path_idx, 0)] for method_id, path_idx in llm_ctx.ep]

            cls_id, scope_id, file_count, symbol_count, behavior_count = llm_ctx.cs
            result["cs"] = [cls_id, scope_id, file_count, symbol_count, behavior_count]

            result["cf"] = []
            for file_entry in llm_ctx.cf:
                file_idx = file_entry[0]
                changed_sym_idxs = list(file_entry[1])
                result["cf"].append([file_idx, changed_sym_idxs])

            result["eg"] = {
                "n": [
                    [
                        sym_idx,
                        depth,
                        old_to_new_idx.get(svc_idx, 0),
                        old_to_new_idx.get(mod_idx, 0)
                    ]
                    for sym_idx, depth, svc_idx, mod_idx in llm_ctx.eg.nodes
                ],
                "e": [list(edge) for edge in llm_ctx.eg.edges],
            }

            result["epts"] = []
            for ep in llm_ctx.epts:
                endpoint_idx, chain_node_idxs, terminal_idx, max_depth = ep
                result["epts"].append(
                    [
                        endpoint_idx,
                        list(chain_node_idxs),
                        old_to_new_idx.get(terminal_idx, 0),
                        max_depth,
                    ]
                )

            result["disc"] = []
            for d in llm_ctx.disc:
                kind_id, facts = d
                result["disc"].append([kind_id, facts])

            return result
        except Exception as exc:
            print(f"[pipeline] LLMContext serialization failed: {exc}")
            import traceback
            traceback.print_exc()
            return None

    def calculate_llm_context_tokens(
        self, serialized_context: dict[str, Any]
    ) -> dict[str, int] | None:
        """
        Calculate token counts for each element in the serialized LLMContext using tiktoken.

        Args:
            serialized_context: The serialized LLMContext dictionary.

        Returns:
            A dictionary mapping each key in LLMContext to its token count, plus a 'total' token count,
            or None if calculation fails.
        """
        if not serialized_context:
            return None

        try:
            # Default to cl100k_base encoding (used by gpt-4, gpt-3.5-turbo, etc.)
            encoding = tiktoken.get_encoding("cl100k_base")

            token_counts: dict[str, int] = {}
            for key, val in serialized_context.items():
                serialized_val = json.dumps(val)
                token_counts[key] = len(encoding.encode(serialized_val))

            # Also calculate the total token count of the entire serialized context
            token_counts["total"] = len(encoding.encode(json.dumps(serialized_context)))
            return token_counts
        except Exception as exc:
            print(f"[pipeline] Token count calculation failed: {exc}")
            return None

    def generate_llm_comment(
        self,
        context: PipelineContext,
        repository: str = "",
        pr_number: str = "",
        language: str = "",
        llm_context_compressed: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate engineering briefing from LLMContext via LLM.

        The LLMContext is sent to the LLM alongside the
        Presentation Compiler prompt, which instructs the model to
        produce an engineering briefing — not a review.

        Args:
            context: Pipeline context with LLMContext
            repository: Repository name
            pr_number: PR number
            language: Programming language

        Returns:
            Dictionary with generated briefing, metadata, raw LLM output
        """
        if context.review_context is None:
            raise PipelineExecutionError(
                "No ReviewContext available for LLM comment generation"
            )
        if context.llm_context is None:
            raise PipelineExecutionError(
                "No LLMContext available for LLM comment generation"
            )

        try:
            from openai import OpenAI

            from core.config import get_settings

            settings = get_settings()

            # Serialize the LLMContext or use provided compressed context
            if llm_context_compressed is not None:
                llm_context_serialized = llm_context_compressed
                llm_context_json = json.dumps(llm_context_compressed, indent=2)
            else:
                llm_context_serialized = self.serialize_llm_context(context)
                llm_context_json = json.dumps(llm_context_serialized, indent=2)

            # Build the Presentation Compiler prompt
            system_prompt = """
You are Factor's Presentation Compiler.

The provided `llm_context` contains deterministic facts extracted from a software
repository and the analyzed change. It may contain:

- changed symbols
- changed files
- callers and callees
- dependency relationships
- execution paths
- fan-in and fan-out
- propagation depth
- service and system boundaries
- event surfaces
- external surfaces
- data surfaces
- validation evidence
- validation gaps
- repository structure

You do NOT have access to the raw diff.

Your job is to reason over the supplied facts and produce ONE SHORT,
HIGH-SIGNAL ENGINEERING DISCOVERY.

The discovery should expose a relationship, execution path, dependency,
boundary, or validation fact that is difficult to understand by looking only
at the changed symbols individually.

The goal is not to summarize the change.

The goal is to answer:

"What did Factor discover by connecting repository facts that would otherwise
require manual investigation?"

CORE PRINCIPLE

Do not maximize coverage.

Maximize information density.

A strong output should cause an engineer to think:

"I didn't realize that path existed."

"I didn't realize this change reaches that part of the system."

"I didn't realize these components depend on this."

"That's something I'd want to investigate."

"Factor saved me from tracing that manually."

The output should expose a concrete repository relationship, not merely describe
what the PR implements.

DISCOVERY SELECTION

Reason over the entire `llm_context` before producing the output.

Look for relationships such as:

- changed symbol → unexpected caller
- changed symbol → distant downstream consumer
- changed symbol → external/system boundary
- changed symbol → event or data propagation
- changed symbol → high fan-in dependency
- changed symbol → high fan-out execution path
- changed symbol → multiple services
- changed entry point → unexpected execution surface
- changed API → previously unrelated subsystem
- changed event → multiple downstream handlers
- changed configuration → multiple execution paths
- changed abstraction → many existing consumers
- changed path → missing validation evidence
- changed behavior → validation that covers only part of the execution path

Prioritize discoveries that are:

1. NON-LOCAL
   The relationship spans multiple symbols, modules, layers, or system
   boundaries.

2. NON-TRIVIAL
   It cannot be explained merely by saying that a changed symbol exists.

3. CONCRETE
   It names actual symbols, paths, callers, consumers, boundaries, or
   validation evidence.

4. INFORMATION-DENSE
   A small amount of text reveals a large amount of repository structure.

5. INVESTIGABLE
   The discovery naturally gives an engineer a specific thing they can inspect.

6. SUPPORTED
   Every factual claim must be directly supported by `llm_context`.

IMPORTANT: DO NOT CONFUSE METRICS WITH DISCOVERIES.

"238 symbols changed" is not a discovery.

"44 event handlers exist" is not a discovery by itself.

"375 boundary crossings" is not a discovery by itself.

However:

"StripeClient.notification_handler() reaches 44 event handlers through
_dispatch(), making StripeClient the common entry point for all of those
notification paths."

is a discovery because it connects multiple deterministic facts into a
meaningful execution relationship.

Similarly:

"An existing StripeClient entry point with 86 upstream callers now reaches
the notification handler path."

is a discovery because it exposes the relationship between an existing
high-fan-in component and the new execution path.

FACTUAL DISCIPLINE

Factor provides evidence, not opinions.

Only state relationships, behavior, and validation facts supported by
`llm_context`.

Do not:

- invent relationships
- infer intent
- speculate about risks
- predict failures
- assign severity
- judge whether the change is good or bad
- recommend code changes
- claim something is insecure unless the supplied facts explicitly establish
  the security property
- turn absence of evidence into a claim that something is broken

You MAY describe an observable property directly.

GOOD:

"The new API exposes an unverified parsing path that bypasses signature
verification."

BAD:

"This introduces a serious security risk."

GOOD:

"No validation evidence was found for the dispatch path handling unlisted
event types."

BAD:

"The dispatch path is likely buggy."

The first versions describe repository facts.
The second versions make unsupported judgments.

INVESTIGATION QUESTION

The final question should point directly at the discovered relationship.

It should NOT ask a generic question such as:

"Is this tested?"

"Is this safe?"

"Does this work?"

It should ask something specific to the discovered structure.

GOOD:

"How does _dispatch() behave when an event type has no registered handler?"

GOOD:

"Which existing StripeClient callers can now reach the notification handler
path?"

GOOD:

"Where is validation established for the 44 event-to-handler mappings?"

BAD:

"Should this be tested?"

BAD:

"Is this architecture safe?"

OUTPUT

Return ONLY valid JSON.

Schema:

{
  "hook": "8-14 word headline describing the discovery",
  "finding": "2-4 concise sentences describing the discovered relationship",
  "evidence": [
    "Deterministic fact supporting the discovery",
    "Optional second supporting fact"
  ],
  "investigate": "One specific question about the discovered relationship"
}

FIELD RULES

hook:

- 8-14 words.
- Describe the discovery, not the PR.
- Make it specific.
- Prefer a concrete symbol or subsystem.
- Avoid generic headlines.

BAD:

"Centralized Event Architecture"

"Large Change to Stripe"

"Improved Notification Handling"

GOOD:

"StripeClient now directly feeds the new notification execution path"

"One client entry point reaches 44 newly introduced event handlers"

finding:

- Maximum 100 words.
- Lead with the most interesting relationship.
- Explain the relationship using concrete repository facts.
- Prefer execution chains and dependency relationships.
- Use exact symbol names when useful.
- Do not repeat the hook verbatim.
- Do not summarize the entire PR.
- Do not include generic background.

evidence:

- Maximum 3 items.
- Each item must be directly supported by `llm_context`.
- Prefer relationships over isolated counts.
- Use metrics only when they strengthen a structural discovery.

investigate:

- Maximum 20 words.
- Must be a specific question about the discovery.
- Must be answerable by inspecting the repository or PR.
- Do not phrase it as a recommendation.

WHAT TO AVOID

Do NOT produce:

- a PR summary
- a code review
- generic architectural commentary
- "Why it matters"
- recommendations
- severity assessments
- speculative risks
- generic testing advice
- lists of every changed component
- raw metric dumps
- claims about intent
- claims about behavior not represented in `llm_context`

Do NOT create a discovery merely because the context contains a large number.

A number becomes useful only when it reveals a relationship.

BAD:

"375 cross-service boundary crossings were found."

GOOD:

"The notification path crosses the StripeClient boundary before dispatching
into the new event-specific handlers, with Factor tracing 375 boundary
crossings across the affected structure."

VALIDATION DISCOVERIES

Validation can be a strong discovery when it is connected to a concrete
execution path.

BAD:

"There are missing tests."

GOOD:

"The notification entry point is validated through the example endpoint, but
Factor found no deterministic validation evidence for the 44 individual
event-handler mappings."

UNVERIFIED DISCOVERIES

Only report an unverified behavior when `llm_context` explicitly establishes
that the relevant path lacks validation evidence.

Do not infer that something is untested merely because no test name appears.

DO NOT FORCE A FINDING

If the context does not contain a genuinely interesting, concrete,
non-local relationship, return:

{
  "hook": "",
  "finding": "",
  "evidence": [],
  "investigate": ""
}

Never manufacture curiosity.

FINAL TEST

Before producing the JSON, internally ask:

1. Is this actually a repository discovery rather than a PR summary?
2. Does it connect at least two meaningful facts?
3. Would an engineer plausibly need repository tracing to discover it?
4. Is every claim supported by `llm_context`?
5. Does the finding tell the engineer exactly what is interesting?
6. Does the investigation question naturally follow from the discovery?

If any answer is NO, select a different discovery or return the empty result.
            """

            user_prompt = (
                f"Repository: {repository or context.repository}\n"
                f"PR: {pr_number}\n"
                f"Language: {language or context.language or 'unknown'}\n\n"
                f"LLMContext:\n{llm_context_json}"
            )

            # Call the LLM
            client = OpenAI(
                api_key=settings.AI_API_KEY,
                base_url=settings.AI_API_BASE_URL,
                timeout=30.0,
            )

            response = client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=4096,
            )

            raw_output = response.choices[0].message.content if response.choices else ""
            model_used = (
                response.model if hasattr(response, "model") else settings.AI_MODEL
            )

            return {
                "generated": True,
                "model": model_used,
                "comment": raw_output
                or "## Analysis Complete\n\nLLM returned empty response.",
                "is_valid": bool(raw_output),
                "validation_errors": [],
                "truncated": False,
                "llm_response": llm_context_serialized,
                "llm_raw_output": raw_output,
            }

        except Exception as exc:
            print(f"[pipeline] LLM comment generation failed: {exc}")
            return {
                "generated": False,
                "model": "fallback",
                "comment": "## ⚠️ Analysis Complete\n\nFactor analysis completed. Please view the full results in the API response.",
                "is_valid": True,
                "validation_errors": [f"LLM generation failed: {exc}"],
                "truncated": False,
                "llm_response": None,
                "llm_raw_output": None,
            }

    async def _compile_overlay_and_view(
        self,
        request: AnalysisRequest,
        base_sha: str,
        head_sha: str,
        language: str,
        context: PipelineContext,
    ) -> tuple[Any, float]:
        """Compile changed files and build RepositoryOverlay & RepositoryView directly from diff."""
        start_time = time.perf_counter()

        # 1. Ensure base snapshot and facts are compiled
        snapshot = context.base_repository_snapshot
        if snapshot is None:
            snapshot = await self.repository_provider.fetch_repository_at_sha(
                request.repository, base_sha
            )
            context.base_repository_snapshot = snapshot

        plugin = self.language_registry.get(language)
        adapter = plugin.create_adapter()

        # Build base facts
        from engine.repository.indexing import InMemoryFactSink, RepositoryIndexer
        from engine.repository.query import InMemoryRepository

        base_sink = InMemoryFactSink()
        base_indexer = RepositoryIndexer(base_sink)
        base_indexer.index_repository(
            {"files": snapshot.files, "language": language}, adapter
        )
        base_facts = base_sink.build_facts()
        base_query = InMemoryRepository(base_facts)

        # 2. Fetch changed files
        changed_files_dict = {}
        if request.pull_request:
            if context.diff_data is None:
                if request.has_diff:
                    context.diff_data = self._diff_snapshot_to_dict(request.diff)
                else:
                    await self._fetch_diff(context, request)

            if context.diff_data and "files" in context.diff_data:

                async def fetch_one(file_path: str):
                    try:
                        if self.repository_provider is None:
                            return file_path, None
                        content = await self.repository_provider.fetch_file(
                            request.repository, file_path, head_sha
                        )
                        return file_path, content
                    except Exception as exc:
                        print(f"[pipeline] File {file_path} not found at head: {exc}")
                        return file_path, None

                tasks = [
                    fetch_one(file_info["file_path"])
                    for file_info in context.diff_data["files"]
                ]
                results = await asyncio.gather(*tasks)
                changed_files_dict = dict(results)

        # 3. Index changed/added files using head indexer sharing base ID maps
        head_sink = InMemoryFactSink()
        head_indexer = RepositoryIndexer(head_sink)
        head_indexer._file_id_map = dict(base_indexer._file_id_map)
        head_indexer._next_file_id = base_indexer._next_file_id
        head_indexer._symbol_id_map = dict(base_indexer._symbol_id_map)
        head_indexer._symbol_fqn_map = dict(base_indexer._symbol_fqn_map)
        head_indexer._next_symbol_id = base_indexer._next_symbol_id

        # Filter files to only index non-None (added/modified)
        files_to_index = {f: c for f, c in changed_files_dict.items() if c is not None}
        head_indexer.index_repository(
            {"files": files_to_index, "language": language}, adapter
        )
        head_facts = head_sink.build_facts()

        # 4. Construct RepositoryOverlay
        from engine.repository.facts import File
        from engine.repository.overlay import RepositoryOverlay, RepositoryView

        added_files = {}
        removed_files = set()
        modified_files = set()

        if context.diff_data:
            for file_info in context.diff_data.get("files", []):
                file_path = file_info["file_path"]
                change_type = file_info.get("change_type")

                if change_type == "added":
                    file_id = head_indexer.get_or_create_file_id(file_path)
                    added_files[file_id] = File(
                        id=file_id, path=file_path, language=language
                    )
                elif change_type == "deleted":
                    file_id = base_indexer._file_id_map.get(file_path)
                    if file_id is not None:
                        removed_files.add(file_id)
                elif change_type == "modified":
                    file_id = base_indexer._file_id_map.get(file_path)
                    if file_id is not None:
                        removed_files.add(file_id)
                        modified_files.add(file_id)
                        added_files[file_id] = File(
                            id=file_id, path=file_path, language=language
                        )

        removed_symbols = {
            s.id for s in base_facts.symbols if s.file_id in removed_files
        }

        overlay = RepositoryOverlay(
            added_files=added_files,
            removed_files=removed_files,
            modified_files=modified_files,
            added_symbols={s.id: s for s in head_facts.symbols},
            removed_symbols=removed_symbols,
            added_calls=set(head_facts.calls),
            added_references=set(head_facts.references),
            added_imports=set(head_facts.imports),
            added_type_relationships=set(head_facts.type_relationships),
            added_endpoints=set(head_facts.endpoints),
            added_database_relationships=set(head_facts.database_relationships),
            added_event_publications=set(head_facts.event_publications),
            added_event_subscriptions=set(head_facts.event_subscriptions),
            added_test_relationships=set(head_facts.test_relationships),
        )

        view = RepositoryView(base_query, overlay)
        duration = time.perf_counter() - start_time
        return view, duration
