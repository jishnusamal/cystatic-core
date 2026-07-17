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
from presentation.compiler import PresentationCompiler
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
                context.diff_data = self._diff_snapshot_to_dict(request.diff) if hasattr(request.diff, 'files') else request.diff
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
            
            # Step 7: Compile presentation IR
            print(f"[pipeline] Step 7: Presentation IR compilation")
            await self._compile_presentation(context)
            print(f"[pipeline] Step 7 done")
            
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
    ) -> RepositoryModel:
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
        snapshot = await self.repository_provider.fetch_repository_at_sha(request.repository, sha)
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

    async def _compile_presentation(self, context: PipelineContext) -> None:
        """
        Compile presentation IR from the engineering discovery model.
        
        Args:
            context: Pipeline context
            
        Raises:
            PipelineExecutionError: If compilation fails
        """
        if context.edm is None:
            raise PipelineExecutionError(
                "Engineering discovery model not available for presentation compilation",
                details={"repository": context.repository},
            )
        
        try:
            import time
            start = time.time()
            
            presentation_compiler = PresentationCompiler()
            context.presentation_ir = presentation_compiler.compile(context.edm)
            
            context.presentation_compile_time = time.time() - start
            context.mark_presentation_compiled()
        except Exception as exc:
            raise PipelineExecutionError(
                f"Presentation compilation failed: {exc}",
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
    
    def render_presentation(self, context: PipelineContext) -> dict[str, Any] | None:
        """
        Render the presentation IR as a dictionary.
        
        Args:
            context: Pipeline context with presentation IR
            
        Returns:
            Dictionary representation of the presentation IR, or None if not available
            
        Raises:
            PipelineExecutionError: If rendering fails
        """
        if context.presentation_ir is None:
            return None
        
        try:
            ir = context.presentation_ir
            return {
                "metadata": {
                    "compiler_version": ir.metadata.compiler_version,
                    "compiled_at": ir.metadata.compiled_at,
                    "discovery_count": ir.metadata.discovery_count,
                    "evidence_count": ir.metadata.evidence_count,
                    "pass_count": ir.metadata.pass_count,
                },
                "summary": {
                    "changed_files": ir.summary.changed_files,
                    "changed_symbols": ir.summary.changed_symbols,
                    "affected_behaviors": ir.summary.affected_behaviors,
                    "execution_paths": ir.summary.execution_paths,
                    "services_reached": ir.summary.services_reached,
                    "validation_gaps": ir.summary.validation_gaps,
                    "surprising_discoveries": ir.summary.surprising_discoveries,
                },
                "discoveries": [
                    {
                        "id": d.id,
                        "kind": d.kind.value,
                        "title": d.title,
                        "summary": d.summary,
                        "compressed": d.compressed,
                        "children": list(d.children) if d.children else [],
                        "source_artifact": d.source_artifact,
                        "evidence": [
                            {
                                "source": e.source,
                                "source_id": e.source_id,
                                "description": e.description,
                                "evidence_ref": e.evidence_ref,
                            }
                            for e in d.evidence
                        ],
                        "metrics": {
                            "execution_reach": d.metrics.execution_reach if d.metrics else 0,
                            "fan_out": d.metrics.fan_out if d.metrics else 0,
                            "propagation_depth": d.metrics.propagation_depth if d.metrics else 0,
                            "boundary_crossings": d.metrics.boundary_crossings if d.metrics else 0,
                            "sharedness": d.metrics.sharedness if d.metrics else 0,
                            "external_surface": d.metrics.external_surface if d.metrics else 0,
                            "data_surface": d.metrics.data_surface if d.metrics else 0,
                            "validation_gap": d.metrics.validation_gap if d.metrics else 0.0,
                            "evidence_density": d.metrics.evidence_density if d.metrics else 0,
                            "cross_domain_evidence": d.metrics.cross_domain_evidence if d.metrics else 0,
                        } if d.metrics else None,
                        "ranking_vector": {
                            "has_external_surface": d.ranking_vector.has_external_surface if d.ranking_vector else 0,
                            "execution_reach": d.ranking_vector.execution_reach if d.ranking_vector else 0,
                            "boundary_crossings": d.ranking_vector.boundary_crossings if d.ranking_vector else 0,
                            "propagation_depth": d.ranking_vector.propagation_depth if d.ranking_vector else 0,
                            "sharedness": d.ranking_vector.sharedness if d.ranking_vector else 0,
                            "has_validation_gap": d.ranking_vector.has_validation_gap if d.ranking_vector else 0,
                            "evidence_density": d.ranking_vector.evidence_density if d.ranking_vector else 0,
                        } if d.ranking_vector else None,
                        "surprise": {
                            "reach_ratio": d.surprise.reach_ratio if d.surprise else 0.0,
                            "propagation_ratio": d.surprise.propagation_ratio if d.surprise else 0.0,
                            "boundary_ratio": d.surprise.boundary_ratio if d.surprise else 0.0,
                            "fan_out_ratio": d.surprise.fan_out_ratio if d.surprise else 0.0,
                            "service_ratio": d.surprise.service_ratio if d.surprise else 0.0,
                            "max_ratio": d.surprise.max_ratio if d.surprise else 0.0,
                            "description": d.surprise.description if d.surprise else "",
                        } if d.surprise else None,
                        "visual_semantic": d.visual_semantic.value if d.visual_semantic else None,
                        "narrative_position": d.narrative_position.value if d.narrative_position else None,
                    }
                    for d in ir.discoveries
                ],
                "narrative": [
                    {
                        "section": n.section,
                        "order": n.order,
                        "discovery_ids": list(n.discovery_ids),
                        "description": n.description,
                    }
                    for n in ir.narrative
                ],
                "visuals": [
                    {
                        "discovery_id": v.discovery_id,
                        "semantic": v.semantic.value,
                        "value": v.value,
                        "label": v.label,
                        "details": v.details,
                    }
                    for v in ir.visuals
                ],
                "evidence": [
                    {
                        "source": e.source,
                        "source_id": e.source_id,
                        "description": e.description,
                        "evidence_ref": e.evidence_ref,
                    }
                    for e in ir.evidence
                ],
                "navigation": ir.navigation,
            }
        except Exception as exc:
            raise PipelineExecutionError(
                f"Presentation rendering failed: {exc}",
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
            return self._github_renderer.render(context.ocm, render_context)
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
            return await self.output_provider.publish(model, destination)
        except Exception as exc:
            raise PipelineExecutionError(
                f"Output publishing failed: {exc}",
                details={"repository": context.repository},
            ) from exc
