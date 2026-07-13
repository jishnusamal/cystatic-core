"""GitHub webhook and API routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from api.schemas.github import AnalysisRequest, AnalysisResponse, WebhookResponse
from api.settings import get_settings
from runtime.errors import InvalidWebhook, MissingWebhookPayload, PipelineExecutionError
from runtime.github_auth import GitHubAppAuth
from runtime.pipeline.context import PipelineContext
from runtime.pipeline.pipeline import Pipeline
from runtime.renderers.github_renderer import GitHubRenderer
from runtime.renderers.json_renderer import JSONRenderer
from source_adapters.github.bot import GitHubWebhookBot

router = APIRouter(tags=["github"])

# Global instances (in production, use dependency injection)
_pipeline: Pipeline | None = None
_github_auth: GitHubAppAuth | None = None


def get_pipeline() -> Pipeline:
    """Get or create the global pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline


def get_github_auth() -> GitHubAppAuth:
    """Get or create the global GitHub App auth instance."""
    global _github_auth
    if _github_auth is None:
        settings = get_settings()
        _github_auth = GitHubAppAuth(
            app_id=settings.GITHUB_APP_CLIENT_ID,
            private_key=settings.GITHUB_PRIVATE_KEY,
            client_secret=settings.GITHUB_CLIENT_SECRET,
        )
    return _github_auth


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
    
    # Verify webhook signature
    signature = request.headers.get("X-Hub-Signature-256")
    webhook_secret = settings.GITHUB_APP_WEBHOOK_SECRET
    
    # Read raw body for signature verification
    body = await request.body()
    
    # Verify signature
    if webhook_secret:
        bot = GitHubWebhookBot()
        if not bot.verify_webhook_signature(body, signature, webhook_secret):
            raise InvalidWebhook("Invalid webhook signature")
    
    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise MissingWebhookPayload("Invalid JSON payload")
    
    # Extract webhook context
    bot = GitHubWebhookBot()
    try:
        context = bot.extract_webhook_context(payload, delivery_id=request.headers.get("X-GitHub-Delivery"))
    except ValueError as exc:
        raise MissingWebhookPayload(str(exc)) from exc
    
    # Check if we should process this event
    event_name = request.headers.get("X-GitHub-Event")
    if not bot.should_process_webhook_event(event_name, context.action):
        return JSONResponse(
            content={"status": "ignored", "message": f"Event {event_name}/{context.action} not processed"},
            status_code=200,
        )
    
    # Extract installation ID for authentication
    installation_id = payload.get("installation", {}).get("id")
    
    # Schedule background analysis
    background_tasks.add_task(
        _process_pr_analysis,
        repository=context.repo,
        pr_number=context.pr_number,
        action=context.action,
        installation_id=installation_id,
        delivery_id=context.delivery_id,
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
    
    try:
        # Run pipeline
        context = await pipeline.run_diff(
            repository=analysis_request.repository,
            base_sha=analysis_request.base_sha or "main",
            head_sha=analysis_request.head_sha or "main",
            diff_data=analysis_request.diff_data or {},
        )
        
        # Render results
        renderer = JSONRenderer()
        result = renderer.render(context.ocm)
        
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
    repository: str,
    pr_number: int,
    action: str,
    installation_id: int | None,
    delivery_id: str | None,
) -> None:
    """
    Background task to process PR analysis.
    
    Args:
        repository: Repository identifier
        pr_number: Pull request number
        action: Webhook action
        installation_id: GitHub App installation ID
        delivery_id: Webhook delivery ID
    """
    settings = get_settings()
    pipeline = get_pipeline()
    
    # Get authenticated GitHub bot for this installation
    github_auth = get_github_auth()
    try:
        bot = github_auth.get_authenticated_bot(installation_id) if installation_id else GitHubWebhookBot()
    except Exception as exc:
        # Log error but don't fail the webhook
        print(f"Failed to authenticate with GitHub: {exc}")
        return
    
    try:
        # Step 1: Fetch PR diff
        print(f"Fetching diff for {repository} PR #{pr_number}")
        diff_ir = bot.fetch_diff(repository, pr_number)
        
        # Convert DiffIR to dict format expected by pipeline
        diff_data = {
            "files": [
                {
                    "file_path": f.file_path,
                    "added_lines": f.added_lines,
                    "removed_lines": f.removed_lines,
                    "hunks": [
                        {
                            "file_path": h.file_path,
                            "source_start": h.source_start,
                            "source_length": h.source_length,
                            "target_start": h.target_start,
                            "target_length": h.target_length,
                            "added_lines": h.added_lines,
                            "removed_lines": h.removed_lines,
                            "lines": [
                                {
                                    "line_type": line.line_type,
                                    "content": line.content,
                                    "source_line_no": line.source_line_no,
                                    "target_line_no": line.target_line_no,
                                }
                                for line in h.lines
                            ],
                        }
                        for h in f.hunks
                    ],
                }
                for f in diff_ir.files
            ]
        }
        
        # Step 2: Get base and head SHAs
        base_sha = bot.get_head_sha(repository, pr_number)  # This gets head, we need base too
        # For now, use head_sha as both (proper implementation would fetch both)
        head_sha = base_sha
        
        # Step 3: Run pipeline
        print(f"Running pipeline for {repository} PR #{pr_number}")
        context = await pipeline.run_pr(
            repository=repository,
            pr_number=pr_number,
            base_sha=base_sha,
            head_sha=head_sha,
            diff_data=diff_data,
            request_id=delivery_id,
            installation_id=installation_id,
        )
        
        if context.error:
            print(f"Pipeline failed for {repository} PR #{pr_number}: {context.error}")
            return
        
        # Step 4: Render GitHub comment using Jinja2 template
        print(f"Rendering GitHub comment for {repository} PR #{pr_number}")
        renderer = GitHubRenderer()
        comment = renderer.render(
            context.ocm,
            {
                "repository": repository,
                "pr_number": pr_number,
                "base_sha": context.base_sha,
                "head_sha": context.head_sha,
                "language": context.language or "unknown",
                "total_time": f"{context.total_time:.2f}" if context.total_time else "N/A",
            },
        )
        
        # Step 5: Post comment to GitHub
        print(f"Posting comment to {repository} PR #{pr_number}")
        bot.post_comment(repository, pr_number, comment)
        
        print(f"Successfully analyzed {repository} PR #{pr_number}")
        
    except Exception as exc:
        # Log error but don't fail the webhook
        print(f"Error processing PR analysis for {repository} PR #{pr_number}: {exc}")
        import traceback
        traceback.print_exc()
