"""GitHub webhook and API routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from api.schemas.github import AnalysisRequest, AnalysisResponse, WebhookResponse
from api.settings import get_settings
from integrations.base import InstallationProvider, OutputProvider, RepositoryProvider
from integrations.base.registry import get_registry
from runtime.errors import InvalidWebhook, MissingWebhookPayload, PipelineExecutionError
from runtime.models import AnalysisTrigger
from runtime.pipeline.context import PipelineContext
from runtime.pipeline.pipeline import Pipeline

router = APIRouter(tags=["github"])

# Global instances (in production, use dependency injection)
_pipeline: Pipeline | None = None
_integration_registry: Any | None = None


def get_integration_registry() -> Any:
    """Get or create the global integration registry."""
    global _integration_registry
    if _integration_registry is None:
        from integrations.github.provider import GitHubIntegration
        _integration_registry = get_registry()
        
        # Register GitHub integration
        settings = get_settings()
        github_integration = GitHubIntegration(
            app_id=settings.GITHUB_APP_CLIENT_ID,
            private_key=settings.GITHUB_PRIVATE_KEY,
            client_secret=settings.GITHUB_CLIENT_SECRET,
            webhook_secret=settings.GITHUB_APP_WEBHOOK_SECRET,
        )
        github_integration.register(_integration_registry)
    
    return _integration_registry


def get_pipeline() -> Pipeline:
    """Get or create the global pipeline instance."""
    global _pipeline
    if _pipeline is None:
        registry = get_integration_registry()
        
        # Get providers from registry
        repository_provider = registry.get_repository_provider("github")
        output_provider = registry.get_output_provider("github")
        
        _pipeline = Pipeline(
            repository_provider=repository_provider,
            output_provider=output_provider,
        )
    return _pipeline


@router.post("/github", response_model=WebhookResponse)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """
    GitHub webhook endpoint for pull request events.
    
    Receives pull_request events (opened, synchronize, reopened, ready_for_review)
    and triggers analysis in the background.
    
    Returns 200 OK immediately and processes the analysis asynchronously.
    """
    settings = get_settings()
    registry = get_integration_registry()
    
    # Get event provider from registry
    event_provider = registry.get_event_provider("github")
    
    # Verify webhook signature
    signature = request.headers.get("X-Hub-Signature-256")
    webhook_secret = settings.GITHUB_APP_WEBHOOK_SECRET
    
    # Read raw body for signature verification
    body = await request.body()
    
    # Verify signature
    if webhook_secret:
        if not await event_provider.verify(body, signature, webhook_secret):
            raise InvalidWebhook("Invalid webhook signature")
    
    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise MissingWebhookPayload("Invalid JSON payload")
    
    # Parse event into AnalysisRequest
    try:
        analysis_request = await event_provider.parse(payload)
    except ValueError as exc:
        raise MissingWebhookPayload(str(exc)) from exc
    
    # Check if this is a pull request event we should process
    if not analysis_request.is_pull_request:
        return JSONResponse(
            content={"status": "ignored", "message": "Not a pull request event"},
            status_code=200,
        )
    
    # Check if we should process this action
    action = analysis_request.metadata.get("action") if analysis_request.metadata else None
    allowed_actions = {"opened", "reopened", "synchronize", "ready_for_review"}
    if action not in allowed_actions:
        return JSONResponse(
            content={"status": "ignored", "message": f"Action {action} not processed"},
            status_code=200,
        )
    
    # Extract installation ID for authentication
    installation_id = analysis_request.metadata.get("installation_id") if analysis_request.metadata else None
    
    # Schedule background analysis
    background_tasks.add_task(
        _process_pr_analysis,
        request=analysis_request,
        installation_id=installation_id,
        delivery_id=analysis_request.metadata.get("delivery_id") if analysis_request.metadata else None,
    )
    
    return JSONResponse(
        content={"status": "accepted", "message": "Analysis scheduled"},
        status_code=200,
    )


@router.post("/v1/analyze", response_model=AnalysisResponse)
async def analyze_repository(
    analysis_request: AnalysisRequest,
) -> AnalysisResponse:
    """
    Public API endpoint to analyze a repository.
    
    Accepts repository references or raw diffs and returns analysis results.
    """
    pipeline = get_pipeline()
    registry = get_integration_registry()
    
    try:
        # Convert API request to runtime model
        from runtime.models import (
            RepositoryReference,
            PullRequestReference,
            DiffSnapshot,
            AnalysisTrigger,
        )
        
        repo_ref = RepositoryReference(
            provider="github",
            owner=analysis_request.repository.split("/")[0],
            repository=analysis_request.repository.split("/")[1],
            default_branch=analysis_request.base_sha or "main",
        )
        
        pr_ref = None
        if analysis_request.pr_number:
            pr_ref = PullRequestReference(
                number=analysis_request.pr_number,
                base_sha=analysis_request.base_sha or "main",
                head_sha=analysis_request.head_sha or "main",
                title="",
            )
        
        diff_snapshot = None
        if analysis_request.diff_data:
            # Convert diff data to DiffSnapshot
            from runtime.models.diff import DiffFile, DiffHunk
            files = []
            for file_data in analysis_request.diff_data.get("files", []):
                hunks = []
                for hunk_data in file_data.get("hunks", []):
                    hunk = DiffHunk(
                        file_path=hunk_data.get("file_path", ""),
                        source_start=hunk_data.get("source_start", 0),
                        source_length=hunk_data.get("source_length", 0),
                        target_start=hunk_data.get("target_start", 0),
                        target_length=hunk_data.get("target_length", 0),
                        added_lines=tuple(hunk_data.get("added_lines", [])),
                        removed_lines=tuple(hunk_data.get("removed_lines", [])),
                        lines=tuple(hunk_data.get("lines", [])),
                    )
                    hunks.append(hunk)
                
                diff_file = DiffFile(
                    file_path=file_data.get("file_path", ""),
                    added_lines=tuple(file_data.get("added_lines", [])),
                    removed_lines=tuple(file_data.get("removed_lines", [])),
                    hunks=tuple(hunks),
                )
                files.append(diff_file)
            
            diff_snapshot = DiffSnapshot(files=tuple(files))
        
        request = AnalysisRequest(
            repository=repo_ref,
            pull_request=pr_ref,
            diff=diff_snapshot,
            trigger=AnalysisTrigger.MANUAL,
        )
        
        # Run pipeline
        context = await pipeline.run(request)
        
        if context.error:
            raise HTTPException(status_code=500, detail=str(context.error))
        
        # Render results
        result = pipeline.render_json(context)
        
        return AnalysisResponse(
            repository=analysis_request.repository,
            language=context.language or "unknown",
            change_summary=result.get("change", {}),
            behavior_summary=result.get("behavior", {}),
            operational_summary={
                k: v for k, v in result.items()
                if k in ["dependency", "data", "event", "api", "validation", "metrics"]
            },
            timing={
                "repository": context.repository_compile_time or 0.0,
                "change": context.change_compile_time or 0.0,
                "behavior": context.behavior_compile_time or 0.0,
                "operational": context.operational_compile_time or 0.0,
                "total": context.total_time or 0.0,
            },
        )
    
    except PipelineExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc.message)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


async def _process_pr_analysis(
    request: AnalysisRequest,
    installation_id: int | None,
    delivery_id: str | None,
) -> None:
    """
    Background task to process PR analysis.
    
    Args:
        request: Analysis request
        installation_id: GitHub App installation ID
        delivery_id: Webhook delivery ID
    """
    pipeline = get_pipeline()
    registry = get_integration_registry()
    
    try:
        # Run pipeline
        context = await pipeline.run(request)
        
        if context.error:
            print(f"Pipeline failed for {request.repository.full_name}: {context.error}")
            return
        
        # Publish output using output provider
        output_provider = registry.get_output_provider("github")
        
        destination = {
            "repo": request.repository.full_name,
            "pr_number": str(request.pull_request.number) if request.pull_request else None,
            "base_sha": request.pull_request.base_sha if request.pull_request else "",
            "head_sha": request.pull_request.head_sha if request.pull_request else "",
            "language": context.language or "unknown",
            "total_time": f"{context.total_time:.2f}" if context.total_time else "N/A",
        }
        
        # Get authentication token if needed
        if installation_id:
            installation_provider = registry.get_installation_provider("github")
            token = await installation_provider.authenticate(str(installation_id))
            destination["token"] = token
        
        await output_provider.publish(context.ocm, destination)
        
        print(f"Successfully analyzed {request.repository.full_name}")
    
    except Exception as exc:
        # Log error but don't fail the webhook
        print(f"Error processing PR analysis for {request.repository.full_name}: {exc}")
        import traceback
        traceback.print_exc()