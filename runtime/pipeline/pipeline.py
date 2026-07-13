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
    """
    
    def __init__(
        self,
        repository_store: RepositoryStore | None = None,
        language_factory: LanguageAdapterFactory | None = None,
    ) -> None:
        """
        Initialize the pipeline.
        
        Args:
            repository_store: Storage backend for repository models
            language_factory: Factory for creating language adapters
        """
        self.repository_store = repository_store
        self.language_factory = language_factory or get_language_factory()
        
        # Compilers (reused across executions)
        self._change_compiler = ChangeCompiler()
        self._behavior_compiler = BehaviorCompiler()
        self._operational_compiler = OperationalCompiler()
        
        # Renderers
        self._json_renderer = JSONRenderer()
        self._github_renderer: GitHubRenderer | None = None
    
    async def run_pr(
        self,
        repository: str,
        pr_number: int,
        base_sha: str | None = None,
        head_sha: str | None = None,
        diff_data: dict[str, Any] | None = None,
        request_id: str | None = None,
        installation_id: str | None = None,
    ) -> PipelineContext:
        """
        Run the pipeline for a pull request.
        
        Args:
            repository: Repository identifier (e.g., "owner/repo")
            pr_number: Pull request number
            base_sha: Base commit SHA
            head_sha: Head commit SHA
            diff_data: Pre-fetched diff data (optional)
            request_id: Request identifier for tracking
            installation_id: GitHub installation ID
            
        Returns:
            PipelineContext with all results
        """
        context = PipelineContext(
            repository=repository,
            base_sha=base_sha,
            head_sha=head_sha,
            diff_data=diff_data,
            request_id=request_id,
            installation_id=installation_id,
        )
        
        try:
            context.mark_compilation_start()
            
            # Step 1: Get or compile repository model
            await self._ensure_repository_model(context)
            
            # Step 2: Fetch diff if not provided
            if context.diff_data is None:
                await self._fetch_diff(context)
            
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
    
    async def run_diff(
        self,
        repository: str,
        base_sha: str,
        head_sha: str,
        diff_data: dict[str, Any],
        request_id: str | None = None,
    ) -> PipelineContext:
        """
        Run the pipeline for a raw diff.
        
        Args:
            repository: Repository identifier
            base_sha: Base commit SHA
            head_sha: Head commit SHA
            diff_data: Raw diff data
            request_id: Request identifier for tracking
            
        Returns:
            PipelineContext with all results
        """
        context = PipelineContext(
            repository=repository,
            base_sha=base_sha,
            head_sha=head_sha,
            diff_data=diff_data,
            request_id=request_id,
        )
        
        try:
            context.mark_compilation_start()
            
            # Step 1: Get or compile repository model
            await self._ensure_repository_model(context)
            
            # Step 2: Compile change model
            await self._compile_change(context)
            
            # Step 3: Compile behavior model
            await self._compile_behavior(context)
            
            # Step 4: Compile operational model
            await self._compile_operational(context)
            
            context.mark_complete()
            
        except Exception as exc:
            context.error = exc
            context.mark_complete()
            raise
        
        return context
    
    async def _ensure_repository_model(self, context: PipelineContext) -> None:
        """
        Ensure repository model is available (load from cache or compile).
        
        Args:
            context: Pipeline context
            
        Raises:
            RepositoryNotSupported: If language is not supported
            RepositoryCompilationFailed: If compilation fails
        """
        # Try to load from cache first
        if self.repository_store is not None:
            ref = context.head_sha or context.base_sha or "main"
            cached_model = await self.repository_store.load(context.repository, ref)
            if cached_model is not None:
                context.repository_model = cached_model
                context.language = cached_model.language
                context.adapter = cached_model.language
                context.mark_repository_compiled()
                return
        
        # Need to compile repository model
        # This requires fetching the repository source
        # For now, raise an error - the actual fetching will be done by the caller
        raise RepositoryNotInstalled(
            "Repository model compilation requires source fetching. "
            "This should be handled by the caller before pipeline execution.",
            details={"repository": context.repository},
        )
    
    async def _fetch_diff(self, context: PipelineContext) -> None:
        """
        Fetch diff for the repository.
        
        Args:
            context: Pipeline context
            
        Raises:
            DiffFetchFailed: If diff fetching fails
        """
        # This is a placeholder - actual diff fetching should be done by the caller
        # The pipeline expects diff_data to be provided
        if context.diff_data is None:
            raise DiffFetchFailed(
                "Diff data not provided. Caller must fetch and provide diff.",
                details={"repository": context.repository},
            )
    
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