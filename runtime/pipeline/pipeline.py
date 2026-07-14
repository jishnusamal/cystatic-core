"""Pipeline orchestrator - the runtime execution engine.

Orchestrates the complete flow from repository/diff to OperationalChangeModel.
No compiler logic - pure orchestration.
"""

from __future__ import annotations

import time
from typing import Any

from change.compiler import ChangeCompiler
from behavior.compiler import BehaviorCompiler
from operational.compiler import OperationalCompiler
from integrations.base import (
    EventProvider,
    InstallationProvider,
    OutputProvider,
    RepositoryProvider,
)
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


class Pipeline:
    """
    Main pipeline orchestrator for runtime execution.
    
    Coordinates the complete flow:
    1. Repository compilation (Phase 1)
    2. Change compilation (Phase 2)
    3. Behavior compilation (Phase 3)
    4. Operational compilation (Phase 4/5)
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
            request_id=request.metadata.get("delivery_id") if request.metadata else None,
        )
        
        try:
            context.mark_compilation_start()
            
            # Step 1: Get or compile repository model
            await self._ensure_repository_model(context, request)
            
            # Step 2: Fetch diff if not provided
            if context.diff_data is None and request.has_diff:
                context.diff_data = self._diff_snapshot_to_dict(request.diff) if hasattr(request.diff, 'files') else request.diff
            
            if context.diff_data is None and self.repository_provider:
                await self._fetch_diff(context, request)
            
            # Step 3: Compile change model
            await self._compile_change(context)
            
            # Step 4: Compile behavior model
            await self._compile_behavior(context)
            
            # Step 5: Compile operational model
            await self._compile_operational(context)
            
            context.mark_complete()
            
        except Exception as exc:
            context.error = exc
            context.mark_complete()
            raise
        
        return context
    
    async def _ensure_repository_model(self, context: PipelineContext, request: AnalysisRequest) -> None:
        """
        Ensure repository model is available (load from cache or compile).
        
        Args:
            context: Pipeline context
            request: Analysis request
            
        Raises:
            RepositoryNotSupported: If language is not supported
            RepositoryCompilationFailed: If compilation fails
        """
        # Try to load from cache first
        if self.repository_store is not None:
            ref = request.pull_request.head_sha if request.pull_request else request.repository.default_branch
            cached_model = await self.repository_store.load(request.repository.full_name, ref)
            if cached_model is not None:
                context.repository_model = cached_model
                context.language = cached_model.metadata.get('language')
                context.adapter = cached_model.metadata.get('language')
                context.mark_repository_compiled()
                return
        
        # Need to compile repository model
        # This requires fetching the repository source
        if self.repository_provider is None:
            raise RepositoryNotInstalled(
                "Repository model compilation requires a repository provider. "
                "No repository provider configured.",
                details={"repository": request.repository.full_name},
            )
        
        # Fetch repository snapshot
        snapshot = await self.repository_provider.fetch_repository(request.repository)
        
        # Detect language and compile
        # This is a simplified version - actual implementation would use language adapters
        raise RepositoryNotInstalled(
            "Repository model compilation from snapshot not yet fully implemented.",
            details={"repository": request.repository.full_name},
        )
    
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
        if context.repository_model is None:
            raise PipelineExecutionError("Repository model not available")
        
        if context.diff_data is None:
            raise InvalidDiff("Diff data not provided")
        
        try:
            context.change_model = self._change_compiler.compile(
                diff_data=context.diff_data,
                old_repository_model=context.repository_model,
                new_repository_model=context.repository_model,
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
        if context.repository_model is None:
            raise PipelineExecutionError("Repository model not available")
        
        if context.change_model is None:
            raise PipelineExecutionError("Change model not available")
        
        try:
            context.behavior_model = self._behavior_compiler.compile(
                change_model=context.change_model,
                repository_model=context.repository_model,
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
        if context.repository_model is None:
            raise PipelineExecutionError("Repository model not available")
        
        if context.change_model is None:
            raise PipelineExecutionError("Change model not available")
        
        if context.behavior_model is None:
            raise PipelineExecutionError("Behavior model not available")
        
        try:
            context.ocm = self._operational_compiler.compile(
                repository_model=context.repository_model,
                change_model=context.change_model,
                behavior_model=context.behavior_model,
            )
            context.mark_operational_compiled()
        except Exception as exc:
            raise PipelineExecutionError(
                f"Operational compilation failed: {exc}",
                details={"repository": context.repository},
            ) from exc
    
    def render_json(self, context: PipelineContext) -> dict[str, Any]:
        """
        Render the pipeline result as JSON.
        
        Args:
            context: Pipeline context with OCM
            
        Returns:
            Dictionary representation
            
        Raises:
            PipelineExecutionError: If rendering fails
        """
        if context.ocm is None:
            raise PipelineExecutionError("No OCM available to render")
        
        try:
            return self._json_renderer.render(context.ocm)
        except Exception as exc:
            raise PipelineExecutionError(
                f"JSON rendering failed: {exc}",
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
            context: Pipeline context with OCM
            pr_number: Pull request number
            
        Returns:
            Markdown string for GitHub comment
            
        Raises:
            PipelineExecutionError: If rendering fails
        """
        if context.ocm is None:
            raise PipelineExecutionError("No OCM available to render")
        
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
            context: Pipeline context with OCM
            destination: Destination information
            
        Returns:
            Published content identifier or None
            
        Raises:
            PipelineExecutionError: If publishing fails
        """
        if context.ocm is None:
            raise PipelineExecutionError("No OCM available to publish")
        
        if self.output_provider is None:
            raise PipelineExecutionError("No output provider configured")
        
        try:
            return await self.output_provider.publish(context.ocm, destination)
        except Exception as exc:
            raise PipelineExecutionError(
                f"Output publishing failed: {exc}",
                details={"repository": context.repository},
            ) from exc