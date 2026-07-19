"""Pipeline orchestrator - the runtime execution engine.

Orchestrates the complete flow from repository/diff to OperationalChangeModel.
No compiler logic - pure orchestration.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from change.compiler import ChangeCompiler
from change.model.repository_comparison import RepositoryComparison
from change.model.repository_delta import RepositoryDelta
from behavior.compiler import BehaviorCompiler
from operational.compiler import OperationalCompiler, EngineeringDiscoveryCompiler
from operational.discovery import DiscoveryCompiler
from review_context.compiler import ReviewContextCompiler
from runtime.errors import (
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
from runtime.language.detection import LanguageAdapterFactory, get_language_factory
from runtime.models import AnalysisRequest, AnalysisTrigger
from runtime.pipeline.context import PipelineContext
from runtime.renderers.github_renderer import GitHubRenderer
from runtime.renderers.json_renderer import JSONRenderer
from runtime.storage.repository_store import RepositoryStore

if TYPE_CHECKING:
    from integrations.base import (
        EventProvider,
        InstallationProvider,
        OutputProvider,
        RepositoryProvider,
    )
    from language_adapters.model import RepositoryModel


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
        context = PipelineContext(
            repository=request.repository.full_name,
            base_sha=request.pull_request.base_sha if request.pull_request else None,
            head_sha=request.pull_request.head_sha if request.pull_request else None,
            request_id=request.metadata.get("delivery_id") if request.metadata else None,
        )
        
        try:
            context.mark_compilation_start()
            
            # Step 1: Compile both base and head repository models
            print(f"[pipeline] Step 1: Repository model compilation for {request.repository.full_name}")
            await self._compile_both_repository_models(context, request)
            print(f"[pipeline] Step 1 done: language={context.language}, base_model={'set' if context.base_repository_model else 'None'}, head_model={'set' if context.head_repository_model else 'None'}")
            
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
            
            # Step 3: Compile change model
            print(f"[pipeline] Step 3: Change model compilation")
            await self._compile_change(context)
            print(f"[pipeline] Step 3 done")
            
            # Step 4: Compile behavior model
            print(f"[pipeline] Step 4: Behavior model compilation")
            await self._compile_behavior(context)
            print(f"[pipeline] Step 4 done")
            
            # Step 5: Compile operational model
            print(f"[pipeline] Step 5: Operational model compilation")
            await self._compile_operational(context)
            print(f"[pipeline] Step 5 done")
            
            # Step 6: Compile engineering discovery model
            print(f"[pipeline] Step 6: Engineering discovery model compilation")
            await self._compile_discovery(context)
            print(f"[pipeline] Step 6 done")
            
            # Step 7: Compile discovery IR (deterministic engineering discoveries)
            print(f"[pipeline] Step 7: Discovery IR compilation")
            await self._compile_discovery_ir(context)
            print(f"[pipeline] Step 7 done")
            
            # Step 8: Compile ReviewContext
            print(f"[pipeline] Step 8: ReviewContext compilation")
            await self._compile_review_context(context)
            print(f"[pipeline] Step 8 done")
            
            context.mark_complete()
            
        except Exception as exc:
            context.error = exc
            context.mark_complete()
            raise
        
        return context
    
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
        
        # Compile base repository model
        print(f"[pipeline] Compiling base repository model at {base_sha}")
        context.base_repository_model = await self._compile_repository_model(
            context, request, base_sha, "base"
        )
        
        # Compile head repository model
        print(f"[pipeline] Compiling head repository model at {head_sha}")
        context.head_repository_model = await self._compile_repository_model(
            context, request, head_sha, "head"
        )
        
        context.mark_repository_compiled()
    
    async def _compile_repository_model(
        self, context: PipelineContext, request: AnalysisRequest, sha: str, label: str
    ) -> RepositoryModel | None:
        """
        Compile a single repository model for a specific SHA.
        
        Args:
            context: Pipeline context
            request: Analysis request
            sha: Commit SHA to compile
            label: Label for logging ("base" or "head")
            
        Returns:
            Compiled RepositoryModel
            
        Raises:
            RepositoryCompilationFailed: If compilation fails
        """
        # Try to load from cache first
        if self.repository_store is not None:
            cached_model = await self.repository_store.load(request.repository.full_name, sha)
            if cached_model is not None:
                print(f"[pipeline] Loaded {label} model from cache")
                # Set language on first load (base or head)
                if context.language is None:
                    context.language = cached_model.metadata.get('language')
                    context.adapter = cached_model.metadata.get('language')
                return cached_model
        
        # Fetch repository snapshot at this SHA
        print(f"[pipeline] Fetching {label} repository snapshot at {sha}")
        snapshot = await self.repository_provider.fetch_repository_at_sha(request.repository, sha)  # type: ignore[union-attr]
        print(f"[pipeline] {label.capitalize()} snapshot: {len(snapshot.files)} files")
        
        # Detect language from repository files (only once)
        if context.language is None:
            print(f"[pipeline] Detecting language from {len(snapshot.files)} files...")
            language = self.language_factory.detect_language(snapshot.files)
            context.language = language
            context.adapter = language
            print(f"[pipeline] Detected language: {language}")
        else:
            language = context.language
        
        # Create language adapter and compile repository model
        adapter = self.language_factory.create_adapter(language)
        print(f"[pipeline] Created {label} adapter: {type(adapter).__name__}")
        
        repository_input = {
            "root_directory": request.repository.full_name,
            "language": language,
            "files": snapshot.files,
            "commit_sha": sha,
        }
        print(f"[pipeline] Compiling {label} repository model with {len(snapshot.files)} files...")
        
        try:
            repository_model = adapter.compile(repository_input)
            print(f"[pipeline] {label.capitalize()} model compiled: {len(repository_model.symbols)} symbols, {len(repository_model.entry_points)} entry points")
        except Exception as exc:
            print(f"[pipeline] {label.capitalize()} repository compilation failed: {exc}")
            raise RepositoryCompilationFailed(
                f"{label.capitalize()} repository compilation failed: {exc}",
                details={"repository": request.repository.full_name, "language": language, "sha": sha},
            ) from exc
        
        # Cache the compiled model if store is available
        if self.repository_store is not None:
            await self.repository_store.save(request.repository.full_name, sha, repository_model)
        
        return repository_model
    
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
                discovery_model=context.edm,
                discovery_ir=context.discovery_ir,
            )
            
            context.presentation_compile_time = time.time() - start
            context.mark_presentation_compiled()
        except Exception as exc:
            raise PipelineExecutionError(
                f"ReviewContext compilation failed: {exc}",
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
                "references": [
                    {
                        "id": r.id,
                        "kind": r.kind,
                        "location": r.location,
                        "compiler_artifact": r.compiler_artifact,
                    }
                    for r in rc.references
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
                "references": [
                    {
                        "id": r.id,
                        "kind": r.kind,
                        "location": r.location,
                        "compiler_artifact": r.compiler_artifact,
                    }
                    for r in rc.references
                ],
            }
        except Exception as exc:
            raise PipelineExecutionError(
                f"LLM context building failed: {exc}",
                details={"repository": context.repository},
            ) from exc
    
    def generate_llm_comment(
        self,
        context: PipelineContext,
        repository: str = "",
        pr_number: str = "",
        language: str = "",
    ) -> dict[str, Any]:
        """
        Generate LLM comment from ReviewContext.
        
        The LLM consumes only ReviewContext — the public ABI of Factor.
        
        Args:
            context: Pipeline context with ReviewContext
            repository: Repository name
            pr_number: PR number
            language: Programming language
            
        Returns:
            Dictionary with generated comment, metadata, and structured LLM response
            
        Raises:
            PipelineExecutionError: If generation fails completely
        """
        if context.review_context is None:
            raise PipelineExecutionError("No ReviewContext available for LLM comment generation")
        
        try:
            from api.settings import get_settings
            
            settings = get_settings()
            
            # Build LLM context from ReviewContext
            llm_context = self.build_llm_context(context)
            
            # Build prompts from ReviewContext
            system_prompt = (
                "You are a code review assistant. "
                "Analyze the following engineering context and produce a structured review. "
                "Only communicate deterministic discoveries. "
                "Never invent new behaviors. "
                "Never speculate about bugs. "
                "Never recommend code changes. "
                "Only summarize deterministic discoveries."
            )
            
            user_prompt = (
                f"Repository: {repository or context.repository}\n"
                f"PR: {pr_number}\n"
                f"Language: {language or context.language or 'unknown'}\n\n"
                f"ReviewContext:\n{llm_context}"
            )
            
            return {
                "generated": True,
                "model": "review_context",
                "comment": "## Analysis Complete\n\nReviewContext generated. LLM comment generation uses ReviewContext as input.",
                "is_valid": True,
                "validation_errors": [],
                "truncated": False,
                "llm_response": llm_context,
                "llm_input": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                },
                "llm_raw_output": None,
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
                "llm_input": None,
                "llm_raw_output": None,
            }
