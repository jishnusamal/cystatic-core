"""Pipeline orchestrator - the runtime execution engine.

Orchestrates the complete flow from repository/diff to OperationalChangeModel.
No compiler logic - pure orchestration.
"""

from __future__ import annotations

import json
import time
import asyncio
from typing import TYPE_CHECKING, Any

from core.logging import timer
from engine.change.compiler import ChangeCompiler
from engine.change.model.repository_comparison import RepositoryComparison
from engine.change.model.repository_delta import RepositoryDelta
from engine.behavior.compiler import BehaviorCompiler
from engine.operational.compiler import OperationalCompiler, EngineeringDiscoveryCompiler
from engine.operational.discovery import DiscoveryCompiler
from engine.review_context.compiler import ReviewContextCompiler
from engine.llm_context.compiler import LLMContextCompiler
from core.errors import (
    CompilationTimeout,
    DiffFetchFailed,
    InvalidDiff,
    LanguageDetectionFailed,
    LanguageNotSupported,
    PipelineExecutionError,
    RepositoryCompilationFailed,
    RepositoryNotInstalled,
    RepositoryNotSupported,
)
from engine.language.detection import LanguageAdapterFactory, get_language_factory
from models import AnalysisRequest, AnalysisTrigger
from engine.pipeline.context import PipelineContext
from integrations.github.renderers.github_renderer import GitHubRenderer
from integrations.github.renderers.json_renderer import JSONRenderer
from engine.repository.indexing import RepositoryStore
import tiktoken

# Custom print wrapper to avoid polluting stdout
def print(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    msg = sep.join(str(arg) for arg in args)
    from core.logging import pipeline_logger
    pipeline_logger.log_pipeline(msg, to_terminal=False)

if TYPE_CHECKING:
    from integrations.base import (
        EventProvider,
        InstallationProvider,
        OutputProvider,
        RepositoryProvider,
    )
    from engine.repository.model import RepositoryModel


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
        language_factory: LanguageAdapterFactory | None = None,
        repository_provider: RepositoryProvider | None = None,
        output_provider: OutputProvider | None = None,
    ) -> None:
        """
        Initialize the pipeline.
        
        Args:
            repository_store: Storage backend for repository models
            language_factory: Factory for creating language adapters
            repository_provider: Provider for fetching repository data
            output_provider: Provider for publishing results
        """
        self.repository_store = repository_store
        self.language_factory = language_factory or get_language_factory()
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
        self._llm_context_compiler = LLMContextCompiler(settings=get_compiler_settings())

        
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
        from core.runtime import RunContext
        from core.logging import pipeline_logger
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
            request_id=request.metadata.get("delivery_id") if request.metadata else None,
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
        
        try:
            context.mark_compilation_start()
            
            with timer.timed("Total Pipeline", metadata={"repository": request.repository.full_name}):
                # Step 1: Compile both base and head repository models
                print(f"[pipeline] Step 1: Repository model compilation for {request.repository.full_name}")
                await self._compile_both_repository_models(context, request)
                print(f"[pipeline] Step 1 done: language={context.language}, base_model={'set' if context.base_repository_model else 'None'}, head_model={'set' if context.head_repository_model else 'None'}")
                
                from core.profile import get_current_profiler
                profiler = get_current_profiler()
                if profiler:
                    profiler.log_memory("After graph construction")
            
            # Step 2: Fetch diff if not provided
            if context.diff_data is None and request.has_diff:
                # request.diff is DiffSnapshot | None, but has_diff ensures it's not None
                assert request.diff is not None
                context.diff_data = self._diff_snapshot_to_dict(request.diff)
                if context.diff_data is not None:
                    print(f"[pipeline] Step 2: Diff provided in request, {len(context.diff_data.get('files', []))} files")
            
            if context.diff_data is None and self.repository_provider:
                print(f"[pipeline] Step 2: Fetching diff from provider")
                await self._fetch_diff(context, request)
                print(f"[pipeline] Step 2 done: {len(context.diff_data.get('files', []))} files in diff" if context.diff_data else "[pipeline] Step 2 done: no diff")
            
            # Step 3: Change Compilation
            change_start = time.perf_counter()
            with timer.timed("Change Compilation"):
                print(f"[pipeline] Step 3: Change model compilation")
                await self._compile_change(context)
                print(f"[pipeline] Step 3 done")
                timer.print_progress()
            change_time = time.perf_counter() - change_start
            if profiler:
                profiler.log_memory("After Change Compiler")
            
            # Step 4: Behavior Compilation
            behavior_start = time.perf_counter()
            with timer.timed("Behavior Compilation"):
                print(f"[pipeline] Step 4: Behavior model compilation")
                await self._compile_behavior(context)
                print(f"[pipeline] Step 4 done")
                timer.print_progress()
            behavior_time = time.perf_counter() - behavior_start
            if profiler:
                profiler.log_memory("After Behavior Compiler")
            
            # Step 5: Operational Compilation
            operational_start = time.perf_counter()
            with timer.timed("Operational Compilation"):
                print(f"[pipeline] Step 5: Operational model compilation")
                await self._compile_operational(context)
                print(f"[pipeline] Step 5 done")
                timer.print_progress()
            operational_time = time.perf_counter() - operational_start
            if profiler:
                profiler.log_memory("After Operational Compiler")
            
            # Step 6: Engineering Discovery Compilation
            discovery_start = time.perf_counter()
            with timer.timed("Engineering Discovery Compilation"):
                print(f"[pipeline] Step 6: Engineering discovery model compilation")
                await self._compile_discovery(context)
                print(f"[pipeline] Step 6 done")
                timer.print_progress()
            discovery_time = time.perf_counter() - discovery_start
            if profiler:
                profiler.log_memory("After Engineering Discovery Compiler")
            
            # Step 7: Discovery IR Compilation
            discovery_ir_start = time.perf_counter()
            with timer.timed("Discovery IR Compilation"):
                print(f"[pipeline] Step 7: Discovery IR compilation")
                await self._compile_discovery_ir(context)
                print(f"[pipeline] Step 7 done")
                timer.print_progress()
            discovery_ir_time = time.perf_counter() - discovery_ir_start
            if profiler:
                profiler.log_memory("After Discovery IR Compiler")
            
            if profiler:
                profiler.log_memory("After system-model construction")
            
            # Step 8: ReviewContext Compilation
            review_start = time.perf_counter()
            with timer.timed("ReviewContext Compilation"):
                print(f"[pipeline] Step 8: ReviewContext compilation")
                await self._compile_review_context(context)
                print(f"[pipeline] Step 8 done")
                timer.print_progress()
            review_time = time.perf_counter() - review_start
            if profiler:
                profiler.log_memory("After ReviewContext Compiler")
            
            # Step 9: LLMContext Compilation
            llm_start = time.perf_counter()
            with timer.timed("LLMContext Compilation"):
                print(f"[pipeline] Step 9: LLMContext compilation")
                await self._compile_llm_context(context)
                print(f"[pipeline] Step 9 done")
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
                pipeline_logger.log_pipeline(f"{stage_text:<38}{time_str}", to_terminal=True)
                
            pipeline_logger.log_pipeline("", to_terminal=True)
            log_stage_time("Change compilation", change_time)
            log_stage_time("Behavior compilation", behavior_time)
            log_stage_time("Operational compilation", operational_time)
            log_stage_time("ReviewContext", review_time)
            log_stage_time("LLMContext", llm_time)
            
            pipeline_logger.log_pipeline("", to_terminal=True)
            total_time = time.perf_counter() - pipeline_start_time
            pipeline_logger.log_pipeline(f"Total: {total_time:.1f}s", to_terminal=True)
            
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
                    "total_time_seconds": round(time.perf_counter() - pipeline_start_time, 3),
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
                            "min_time": round(stats.min_time, 4) if stats.min_time != float("inf") else 0,
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
            snapshot = await self.repository_provider.fetch_repository_at_sha(request.repository, base_sha)
        except Exception as exc:
            raise RepositoryCompilationFailed(
                f"Failed to fetch base repository at {base_sha}: {exc}",
                details={"repository": request.repository.full_name, "sha": base_sha},
            ) from exc
        base_fetch_time = time.perf_counter() - base_fetch_start
        print(f"[pipeline] Base snapshot fetched: {len(snapshot.files)} files")
        
        # Detect language
        if context.language is None:
            print(f"[pipeline] Detecting language from {len(snapshot.files)} files...")
            language = self.language_factory.detect_language(snapshot.files)
            context.language = language
            context.adapter = language
            print(f"[pipeline] Detected language: {language}")
        else:
            language = context.language
        
        adapter = self.language_factory.create_adapter(language)
        
        base_compile_start = time.perf_counter()
        repository_input = {
            "root_directory": request.repository.full_name,
            "language": language,
            "files": snapshot.files,
            "commit_sha": base_sha,
        }
        print(f"[pipeline] Compiling base RepositoryGraph...")
        try:
            from core.profile import get_current_profiler
            profiler = get_current_profiler()
            if profiler:
                profiler.log_memory("After base repository download")
            base_graph = adapter.compile_graph(repository_input)
        except Exception as exc:
            raise RepositoryCompilationFailed(
                f"Base repository compilation failed: {exc}",
                details={"repository": request.repository.full_name, "language": language, "sha": base_sha},
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
                        print(f"[pipeline] File {file_path} not found at head (assumed deleted): {exc}")
                        return file_path, None
                
                tasks = [fetch_one(file_info["file_path"]) for file_info in context.diff_data["files"]]
                results = await asyncio.gather(*tasks)
                changed_files_dict = dict(results)
        
        changed_fetch_time = time.perf_counter() - changed_fetch_start
        
        from core.profile import get_current_profiler
        profiler = get_current_profiler()
        if profiler:
            profiler.log_memory("After GitHub/API data retrieval")
            profiler.log_memory("After head source load")
        
        # Clone base_graph using pickle to avoid mutating cache
        from core.logging import pipeline_logger
        import pickle
        pipeline_logger.log_pipeline("[pipeline] Step 1.2: Cloning base RepositoryGraph for head compilation...", to_terminal=True)
        clone_start = time.perf_counter()
        if profiler:
            profiler.log_memory("Before graph clone")
            profiler.start_sub_peak_tracking()
        patched_graph = pickle.loads(pickle.dumps(base_graph))
        if profiler:
            peak_during_clone = profiler.stop_sub_peak_tracking()
            profiler.checkpoints["peak during graph clone"] = {
                "current_rss": profiler.process.memory_info().rss / (1024 * 1024),
                "peak_rss": peak_during_clone
            }
            profiler.log_memory("After graph clone")
        clone_duration = time.perf_counter() - clone_start
        pipeline_logger.log_pipeline(f"[pipeline] Step 1.2 done: Base graph cloned in {clone_duration:.2f}s", to_terminal=True)
        
        # Compile changes incrementally on patched_graph
        metrics: dict[str, Any] = {}
        incremental_start = time.perf_counter()
        
        adapter = self.language_factory.create_adapter(language)
        repository_input = {
            "files": changed_files_dict,
            "changed_only": True,
            "metrics": metrics,
            "language": language,
        }
        
        pipeline_logger.log_pipeline(f"[pipeline] Step 1.3: Running incremental compilation for {len(changed_files_dict)} changed files...", to_terminal=True)
        try:
            from core.logging import timer
            with timer.timed("Incremental Compilation"):
                patched_graph = adapter.compile_incremental(patched_graph, repository_input)
        except Exception as exc:
            raise RepositoryCompilationFailed(
                f"Incremental compilation failed: {exc}",
                details={"repository": request.repository.full_name, "language": language, "sha": head_sha},
            ) from exc
            
        changed_compile_time = metrics.get("compile_duration", time.perf_counter() - incremental_start)
        patch_duration = metrics.get("patch_duration", 0.0)
        
        return patched_graph, changed_fetch_time, clone_duration, changed_compile_time, patch_duration, metrics

    async def _compile_both_repository_models(self, context: PipelineContext, request: AnalysisRequest) -> None:
        """
        Compile both base and head repository models.
        
        Args:
            context: Pipeline context
            request: Analysis request
            
        Raises:
            RepositoryNotInstalled: If repository provider is not configured
            RepositoryCompilationFailed: If compilation fails
        """
        if self.repository_provider is None:
            raise RepositoryNotInstalled(
                "Repository model compilation requires a repository provider. "
                "No repository provider configured.",
                details={"repository": request.repository.full_name},
            )
        
        # Determine which SHAs to compile
        if request.pull_request:
            base_sha = request.pull_request.base_sha
            head_sha = request.pull_request.head_sha
        else:
            # For non-PR analysis, use default branch for both
            base_sha = request.repository.default_branch
            head_sha = request.repository.default_branch
        
        context.base_sha = base_sha
        context.head_sha = head_sha
        
        from core.logging import pipeline_logger
        from engine.repository.model import RepositoryGraph
        import time
        import asyncio
        
        with timer.timed("Repository Compilation", metadata={"base_sha": base_sha, "head_sha": head_sha}):
            # --- Base Repository Graph Stage ---
            print(f"[pipeline] Compiling base repository graph at {base_sha}")
            base_fetch_start = time.perf_counter()
            base_cached = False
            base_graph = None
            
            if self.repository_store is not None:
                try:
                    cached_obj = await self.repository_store.load(request.repository.full_name, base_sha)
                    if isinstance(cached_obj, RepositoryGraph):
                        base_graph = cached_obj
                        base_cached = True
                        print(f"[pipeline] Loaded base RepositoryGraph from cache")
                        from core.profile import get_current_profiler
                        profiler = get_current_profiler()
                        if profiler:
                            profiler.log_memory("After base graph load")
                except Exception as exc:
                    print(f"[pipeline] Failed to load base from cache: {exc}")
            
            if base_graph is None:
                base_graph, base_fetch_time, base_compile_time, language = await self._compile_base_graph(
                    request, base_sha, context
                )
                from core.profile import get_current_profiler
                profiler = get_current_profiler()
                if profiler:
                    profiler.log_memory("After base graph compilation")
                
                # Save base graph to cache
                if self.repository_store is not None:
                    try:
                        await self.repository_store.save(request.repository.full_name, base_sha, base_graph)
                    except Exception as exc:
                        print(f"[pipeline] Failed to save base graph to cache: {exc}")
            else:
                base_fetch_time = time.perf_counter() - base_fetch_start
                base_compile_time = 0.0
                if context.language is None:
                    language = base_graph.metadata.get("language", "python")
                    context.language = language
                    context.adapter = language
                else:
                    language = context.language
            
            # Export base RepositoryModel
            base_export_start = time.perf_counter()
            context.base_repository_model = base_graph.to_model()
            base_export_duration = time.perf_counter() - base_export_start
            from core.profile import get_current_profiler
            profiler = get_current_profiler()
            if profiler:
                profiler.log_memory("After base RepositoryModel")
            
            base_files_compiled = 0 if base_cached else len(base_graph.files)
            timer.print_progress()
            
            # --- Head Repository Incremental Stage ---
            print(f"[pipeline] Compiling head repository incrementally at {head_sha}")
            
            patched_graph, changed_fetch_time, clone_duration, changed_compile_time, patch_duration, metrics = await self._compile_head_graph(
                request, head_sha, base_graph, language, context
            )
            
            if profiler:
                profiler.log_memory("After GraphPatcher")
            
            # Export head RepositoryModel
            pipeline_logger.log_pipeline("[pipeline] Step 1.4: Exporting head RepositoryModel via patched_graph.to_model()...", to_terminal=True)
            head_export_start = time.perf_counter()
            with timer.timed("RepositoryGraph.to_model"):
                context.head_repository_model = patched_graph.to_model()
            head_export_duration = time.perf_counter() - head_export_start
            if profiler:
                profiler.log_memory("After head RepositoryModel")
            pipeline_logger.log_pipeline(f"[pipeline] Step 1.4 done: Head RepositoryModel exported in {head_export_duration:.2f}s", to_terminal=True)
            
            timer.print_progress()
            
        context.mark_repository_compiled()
        
        # Overview log output to terminal
        pipeline_logger.log_pipeline("[Pipeline] Repository compilation", to_terminal=True)
        
        base_fetch_str = "cached" if base_cached else f"{base_fetch_time:.1f}s"
        pipeline_logger.log_pipeline(f"  ✓ Fetch base repository ({base_fetch_str})", to_terminal=True)
        
        base_compile_str = "cached" if base_cached else f"{base_compile_time:.1f}s"
        pipeline_logger.log_pipeline(f"  ✓ Compile base graph ({base_compile_str})", to_terminal=True)
        
        changed_fetch_str = f"{changed_fetch_time:.1f}s"
        pipeline_logger.log_pipeline(f"  ✓ Fetch changed files ({changed_fetch_str})", to_terminal=True)
        
        changed_compile_str = f"{changed_compile_time:.1f}s"
        pipeline_logger.log_pipeline(f"  ✓ Compile changed files ({changed_compile_str})", to_terminal=True)
        
        patch_duration_str = f"{patch_duration:.1f}s"
        pipeline_logger.log_pipeline(f"  ✓ Patch repository graph ({patch_duration_str})", to_terminal=True)
        
        export_duration_str = f"{head_export_duration:.1f}s"
        pipeline_logger.log_pipeline(f"  ✓ Export RepositoryModel ({export_duration_str})", to_terminal=True)
        
        # Telemetry detail logging
        changed_files_compiled = metrics.get("changed_files_compiled", 0)
        files_skipped = metrics.get("files_skipped", len(base_graph.files))
        symbols_replaced = metrics.get("symbols_replaced", 0)
        symbols_inserted = metrics.get("symbols_inserted", 0)
        symbols_removed = metrics.get("symbols_removed", 0)
        edges_updated = metrics.get("edges_updated", 0)
        
        pipeline_logger.log_pipeline("", to_terminal=True)
        pipeline_logger.log_pipeline(f"  Base files compiled: {base_files_compiled}", to_terminal=True)
        pipeline_logger.log_pipeline(f"  Changed files compiled: {changed_files_compiled}", to_terminal=True)
        pipeline_logger.log_pipeline(f"  Files skipped: {files_skipped}", to_terminal=True)
        pipeline_logger.log_pipeline(f"  Symbols replaced: {symbols_replaced}", to_terminal=True)
        pipeline_logger.log_pipeline(f"  Symbols inserted: {symbols_inserted}", to_terminal=True)
        pipeline_logger.log_pipeline(f"  Symbols removed: {symbols_removed}", to_terminal=True)
        pipeline_logger.log_pipeline(f"  Edges updated: {edges_updated}", to_terminal=True)
        pipeline_logger.log_pipeline(f"  Patch duration: {patch_duration:.3f}s", to_terminal=True)
        pipeline_logger.log_pipeline(f"  Export duration: {head_export_duration:.3f}s", to_terminal=True)

    
    async def _fetch_diff(self, context: PipelineContext, request: AnalysisRequest) -> None:
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
        Compile change model.
        
        Args:
            context: Pipeline context
            
        Raises:
            InvalidDiff: If diff data is invalid
            PipelineExecutionError: If compilation fails
        """
        # Validate invariants before compilation
        if context.base_repository_model is None:
            raise PipelineExecutionError(
                "Base repository model not available",
                details={"repository": context.repository, "base_sha": context.base_sha},
            )
        
        if context.head_repository_model is None:
            raise PipelineExecutionError(
                "Head repository model not available",
                details={"repository": context.repository, "head_sha": context.head_sha},
            )
        
        if context.diff_data is None:
            raise InvalidDiff(
                "Diff data not provided",
                details={"repository": context.repository},
            )
        
        # Validate that base and head are different (unless same SHA)
        if context.base_sha == context.head_sha:
            print(f"[pipeline] Warning: Base and head SHAs are identical ({context.base_sha})")
        
        try:
            # Create RepositoryDelta - the canonical input for all downstream phases
            context.repository_delta = RepositoryDelta(
                base_model=context.base_repository_model,
                head_model=context.head_repository_model,
                diff=context.diff_data,
                base_sha=context.base_sha or "",
                head_sha=context.head_sha or "",
            )
            
            # Create a RepositoryComparison - the dedicated input model for ChangeCompiler
            comparison = RepositoryComparison(
                base_model=context.base_repository_model,
                head_model=context.head_repository_model,
                diff=context.diff_data,
                base_sha=context.base_sha or "",
                head_sha=context.head_sha or "",
            )
            
            # Compile with the dedicated input model
            context.change_model = self._change_compiler.compile(
                comparison=comparison
            )
            context.mark_change_compiled()
        except Exception as exc:
            raise PipelineExecutionError(
                f"Change compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc
    
    async def _compile_behavior(self, context: PipelineContext) -> None:
        """
        Compile behavior model.
        
        Args:
            context: Pipeline context
            
        Raises:
            PipelineExecutionError: If compilation fails
        """
        # Validate invariants before compilation
        if context.repository_delta is None:
            raise PipelineExecutionError(
                "Repository delta not available",
                details={"repository": context.repository},
            )
        
        if context.change_model is None:
            raise PipelineExecutionError(
                "Change model not available",
                details={"repository": context.repository},
            )
        
        try:
            # BehaviorCompiler receives repository_delta for cross-model analysis
            context.behavior_model = self._behavior_compiler.compile(
                change_model=context.change_model,
                repository_delta=context.repository_delta,
            )
            context.mark_behavior_compiled()
        except Exception as exc:
            raise PipelineExecutionError(
                f"Behavior compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc
    
    async def _compile_operational(self, context: PipelineContext) -> None:
        """
        Compile operational change model.
        
        Args:
            context: Pipeline context
            
        Raises:
            PipelineExecutionError: If compilation fails
        """
        # Validate invariants before compilation
        if context.repository_delta is None:
            raise PipelineExecutionError(
                "Repository delta not available",
                details={"repository": context.repository},
            )
        
        if context.change_model is None:
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
            # OperationalCompiler receives repository_delta for cross-model validation
            context.ocm = self._operational_compiler.compile(
                repository_delta=context.repository_delta,
                change_model=context.change_model,
                behavior_model=context.behavior_model,
            )
            context.mark_operational_compiled()
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
            context.edm = self._discovery_compiler.from_operational_model(
                context.ocm
            )
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
                "total_time": f"{context.total_time:.2f}" if context.total_time else "N/A",
            }
            
            # Prefer EDM over OCM
            if context.edm is not None:
                return self._github_renderer.render_artifact(context.edm, render_context)
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
            raise PipelineExecutionError("No ReviewContext available for LLM context building")
        
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
            strings = llm_ctx.st.entries
            
            def resolve(idx: int) -> str:
                return strings[idx] if idx < len(strings) else ""
            
            # Serialize string table
            result: dict[str, Any] = {
                "st": list(strings),
            }
            
            # Serialize lookup tables — keep as compact lists of ints
            result["f"] = [list(e) for e in llm_ctx.f]
            result["sym"] = [list(s) for s in llm_ctx.sym]
            result["ep"] = [list(e) for e in llm_ctx.ep]
            
            # Serialize change section
            cls_id, scope_id, file_count, symbol_count, behavior_count = llm_ctx.cs
            result["cs"] = [cls_id, scope_id, file_count, symbol_count, behavior_count]
            
            result["cf"] = []
            for file_entry in llm_ctx.cf:
                file_idx = file_entry[0]
                changed_sym_idxs = list(file_entry[1])
                result["cf"].append([file_idx, changed_sym_idxs])
            
            # Serialize execution section
            result["eg"] = {
                "n": [list(node) for node in llm_ctx.eg.nodes],
                "e": [list(edge) for edge in llm_ctx.eg.edges],
            }
            
            result["epts"] = []
            for ep in llm_ctx.epts:
                endpoint_idx, chain_node_idxs, terminal_idx, max_depth = ep
                result["epts"].append([
                    endpoint_idx,
                    list(chain_node_idxs),
                    terminal_idx,
                    max_depth,
                ])
            
            # Serialize discoveries
            result["disc"] = []
            for d in llm_ctx.disc:
                kind_id, facts = d
                result["disc"].append([kind_id, facts])
            
            return result
        except Exception as exc:
            print(f"[pipeline] LLMContext serialization failed: {exc}")
            return None

    def calculate_llm_context_tokens(self, serialized_context: dict[str, Any]) -> dict[str, int] | None:
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
            raise PipelineExecutionError("No ReviewContext available for LLM comment generation")
        if context.llm_context is None:
            raise PipelineExecutionError("No LLMContext available for LLM comment generation")
        
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
            system_prompt = (
                "You are Factor's Presentation Compiler.\n\n"
                "The provided `llm_context` contains deterministic engineering facts. "
                "Do not review code, speculate, recommend changes, or invent information.\n\n"
                "Your job is to create an engineering briefing that gives the reader an immediate "
                '\u201caha\u201d moment.\n\n'
                "Do not answer \u201cWhat changed?\u201d\n\n"
                "Answer:\n"
                "\u201cWhy do I suddenly understand this PR much better than I did from GitHub alone?\u201d\n\n"
                "Prioritize:\n"
                "- Hidden relationships\n"
                "- Unexpected execution paths\n"
                "- Blast radius and scale\n"
                "- Hidden consequences\n"
                "- Connected context\n"
                "- Manual investigation eliminated\n\n"
                "Prefer consequences over implementation.\n"
                "Prefer relationships over lists.\n"
                "Prefer quantities over names.\n"
                "Compress aggressively. Every sentence should reveal something an experienced engineer "
                "is unlikely to discover quickly by reading the PR.\n\n"
                "The briefing should make the reader think:\n"
                '- \u201cI didn\u2019t know that.\u201d\n'
                '- \u201cI wouldn\u2019t have found that this quickly.\u201d\n'
                '- \u201cThat\u2019s a much larger change than I expected.\u201d\n'
                '- \u201cThis replaced the investigation I normally do.\u201d\n\n'
                "## Output\n\n"
                "# Biggest Discovery\n"
                "One sentence describing the most important architectural or operational consequence.\n\n"
                "# Why It Matters\n"
                "3\u20135 bullets explaining the hidden relationships or consequences introduced by the change.\n\n"
                "# Hidden Reach\n"
                "Show how the change propagates through the system "
                "(services, APIs, events, databases, consumers, etc.). "
                "Prefer connected chains over lists.\n\n"
                "# Scale\n"
                "Quantify the impact "
                "(files, symbols, behaviors, services, endpoints, consumers, execution paths, etc.) "
                "to demonstrate the true size of the change.\n\n"
                "# Validation Context\n"
                "Summarize deterministic validation evidence and relate it to the affected execution paths. "
                "Do not speculate about missing tests.\n\n"
                "# Investigation Replaced\n"
                "List the engineering work this analysis eliminated "
                "(dependency tracing, execution mapping, downstream impact analysis, validation discovery, etc.).\n\n"
                "If a section doesn\u2019t increase understanding beyond what GitHub already shows, omit it."
            )
            
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
            model_used = response.model if hasattr(response, 'model') else settings.AI_MODEL
            
            return {
                "generated": True,
                "model": model_used,
                "comment": raw_output or "## Analysis Complete\n\nLLM returned empty response.",
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
