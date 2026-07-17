"""GitHub integration routes for FastAPI."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from integrations.base import InstallationProvider, OutputProvider, RepositoryProvider
from integrations.base.registry import get_registry
from integrations.github.client import GitHubClient
from runtime.errors import InvalidWebhook, MissingWebhookPayload, PipelineExecutionError
from runtime.models import AnalysisRequest, AnalysisTrigger
from runtime.pipeline.context import PipelineContext
from runtime.pipeline.pipeline import Pipeline

router = APIRouter(tags=["github"])

# Global instances (in production, use dependency injection)
_pipeline: Pipeline | None = None
_registry: Any | None = None


def get_registry_instance() -> Any:
    """Get or create the global integration registry."""
    global _registry
    if _registry is None:
        from integrations.github.provider import GitHubIntegration
        from api.settings import get_settings
        
        _registry = get_registry()
        
        # Register GitHub integration
        settings = get_settings()
        github_integration = GitHubIntegration(
            app_id=settings.GITHUB_APP_CLIENT_ID,
            private_key=settings.GITHUB_PRIVATE_KEY,
            client_secret=settings.GITHUB_CLIENT_SECRET,
            webhook_secret=settings.GITHUB_APP_WEBHOOK_SECRET,
        )
        github_integration.register(_registry)
    
    return _registry


def get_pipeline_instance() -> Pipeline:
    """Get or create the global pipeline instance."""
    global _pipeline
    if _pipeline is None:
        registry = get_registry_instance()
        
        # Get providers from registry
        repository_provider = registry.get_repository_provider("github")
        output_provider = registry.get_output_provider("github")
        
        _pipeline = Pipeline(
            repository_provider=repository_provider,
            output_provider=output_provider,
        )
    return _pipeline


@router.post("/github", response_model=dict[str, Any])
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """
    GitHub webhook endpoint for pull request events.
    
    Receives pull_request events (opened, synchronize, reopened, ready_for_review)
    and triggers analysis in the background. The webhook signature is verified
    using the configured webhook secret, and analysis is scheduled asynchronously.
    
    Input:
        - Headers:
            - X-Hub-Signature-256 (str, optional): HMAC-SHA256 signature for webhook verification
            - Content-Type: application/json
        - Body (JSON): GitHub webhook payload containing pull request event data
    
    Returns:
        JSONResponse: Webhook processing status:
            - status (str): "accepted" if analysis scheduled, "ignored" if event not processed
            - message (str): Human-readable status message
    
    Example Responses:
        Accepted:
        {
            "status": "accepted",
            "message": "Analysis scheduled"
        }
        
        Ignored (not a PR):
        {
            "status": "ignored",
            "message": "Not a pull request event"
        }
        
        Ignored (unsupported action):
        {
            "status": "ignored",
            "message": "Action ready_for_review not processed"
        }
    
    Status Codes:
        200: Webhook received and processed (or ignored if not a supported event)
        400: Invalid JSON payload or missing required fields
        401: Invalid webhook signature (when webhook secret is configured)
    
    Notes:
        - Returns 200 OK immediately and processes analysis asynchronously
        - Only processes actions: opened, reopened, synchronize, ready_for_review
        - Requires GitHub App webhook secret to be configured for signature verification
        - Analysis results are posted as a comment on the pull request
    """
    from api.settings import get_settings
    
    settings = get_settings()
    registry = get_registry_instance()
    
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


@router.post("/v1/analyze", response_model=dict[str, Any])
async def analyze_repository(
    analysis_request: dict[str, Any],
) -> JSONResponse:
    """
    Public API endpoint to analyze a repository.
    
    Accepts repository references, PR URLs, or raw diffs and returns comprehensive analysis
    results including change summary, behavior summary, and operational summary.
    
    Input:
        Request body (JSON) with the following fields (Option 1 - PR URL):
            - pr_url (str, required): GitHub PR URL (e.g., "https://github.com/owner/repo/pull/123")
        
        OR (Option 2 - Structured data):
            - repository (str, required): Repository in format "owner/repo"
            - pr_number (int, optional): Pull request number to analyze
            - base_sha (str, optional): Base commit SHA (default: "main")
            - head_sha (str, optional): Head commit SHA (default: "main")
            - diff_data (dict, optional): Raw diff data with structure:
                - files (list): List of diff files, each containing:
                    - file_path (str): Path to the file
                    - added_lines (list): Lines added in the diff
                    - removed_lines (list): Lines removed in the diff
                    - hunks (list, optional): Diff hunks with detailed changes
    
    Returns:
        JSONResponse: Comprehensive analysis results:
            - repository (str): Analyzed repository name
            - language (str): Detected programming language
            - change_summary (dict): Summary of code changes
            - behavior_summary (dict): Summary of behavior changes
            - operational_summary (dict): Summary of operational impacts:
                - dependency (dict): Dependency changes
                - data (dict): Data model changes
                - event (dict): Event changes
                - api (dict): API changes
                - validation (dict): Validation changes
                - metrics (dict): Metrics changes
            - timing (dict): Compilation and execution timing:
                - repository (float): Repository compilation time in seconds
                - change (float): Change compilation time in seconds
                - behavior (float): Behavior compilation time in seconds
                - operational (float): Operational compilation time in seconds
                - total (float): Total execution time in seconds
    
    Example Request (PR URL):
        {
            "pr_url": "https://github.com/huggingface/OpenEnv/pull/611"
        }
    
    Example Request (Structured):
        {
            "repository": "owner/repo-name",
            "pr_number": 123,
            "base_sha": "abc123",
            "head_sha": "def456"
        }
    
    Example Response:
        {
            "repository": "owner/repo-name",
            "language": "python",
            "change_summary": {...},
            "behavior_summary": {...},
            "operational_summary": {
                "dependency": {...},
                "data": {...}
            },
            "timing": {
                "repository": 0.15,
                "change": 0.08,
                "behavior": 0.12,
                "operational": 0.05,
                "total": 0.40
            }
        }
    
    Status Codes:
        200: Analysis completed successfully
        400: Invalid request format or missing required fields
        500: Analysis failed due to internal error
    
    Notes:
        - Either pr_url, (pr_number + repository), or diff_data can be provided
        - If pr_url is provided, the system will automatically fetch PR details from GitHub
        - If diff_data is provided, it will be analyzed directly without fetching from GitHub
        - Analysis includes change detection, behavior analysis, and operational impact assessment
    """
    pipeline = get_pipeline_instance()
    registry = get_registry_instance()
    
    print("[routes] /v1/analyze called")
    
    try:
        # Convert API request to runtime model
        from runtime.models import (
            RepositoryReference,
            PullRequestReference,
            DiffSnapshot,
            AnalysisTrigger,
        )
        from runtime.models.diff import DiffFile, DiffHunk
        
        # Check if PR URL is provided
        pr_url = analysis_request.get("pr_url")
        if pr_url:
            print(f"[routes] Fetching PR details from URL: {pr_url}")
            # Parse PR URL and fetch PR details from GitHub
            pr_data = await _fetch_pr_details_from_url(pr_url)
            print(f"[routes] PR details: repo={pr_data['repository']}, PR=#{pr_data['pr_number']}, base={pr_data['base_sha']}, head={pr_data['head_sha']}")
            repository = pr_data["repository"]
            pr_number = pr_data["pr_number"]
            base_sha = pr_data["base_sha"]
            head_sha = pr_data["head_sha"]
        else:
            # Use structured data
            repository = analysis_request.get("repository")
            pr_number = analysis_request.get("pr_number")
            base_sha = analysis_request.get("base_sha")
            head_sha = analysis_request.get("head_sha")
            
            if not repository:
                raise HTTPException(
                    status_code=400,
                    detail="Either 'pr_url' or 'repository' must be provided"
                )
        
        repo_ref = RepositoryReference(
            provider="github",
            owner=repository.split("/")[0],
            repository=repository.split("/")[1],
            default_branch=base_sha or "main",
        )
        
        pr_ref = None
        if pr_number:
            pr_ref = PullRequestReference(
                number=pr_number,
                base_sha=base_sha or "main",
                head_sha=head_sha or "main",
                title="",
            )
        
        diff_snapshot = None
        if analysis_request.get("diff_data"):
            files = []
            for file_data in analysis_request["diff_data"].get("files", []):
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
        
        analysis_request_obj = AnalysisRequest(
            repository=repo_ref,
            pull_request=pr_ref,
            diff=diff_snapshot,
            trigger=AnalysisTrigger.MANUAL,
        )
        
        # Run pipeline
        print(f"[routes] Starting pipeline run for {repo_ref.full_name}")
        context = await pipeline.run(analysis_request_obj)
        print(f"[routes] Pipeline completed: language={context.language}, total_time={context.total_time:.2f}s")
        
        if context.error:
            print(f"[routes] Pipeline error: {context.error}")
            raise HTTPException(status_code=500, detail=str(context.error))
        
        # Render results (prefers EDM over OCM)
        result = pipeline.render_json(context)
        
        # Extract the discovery data from the rendered JSON
        # EDM renders include an "execution" key; OCM renders do not
        discovery_summary = result.get("execution")
        if discovery_summary is not None:
            # EDM path: include enrichment models projected into discovery
            discovery_summary = dict(discovery_summary)
            for model_name in ["dependency", "data", "event", "api", "validation", "metrics"]:
                if model_name in result:
                    discovery_summary[model_name] = result[model_name]
        elif context.ocm is not None:
            # Fallback: project execution data from OCM behavior model
            discovery_summary = {
                "behaviors_count": len(context.ocm.behavior.behaviors),
                "execution_chains_count": len(context.ocm.behavior.execution_chains),
                "entry_points_count": len(context.ocm.behavior.entry_points),
                "terminal_points_count": len(context.ocm.behavior.terminal_points),
                "execution_depth": context.ocm.behavior.execution_depth,
            }
            # Include available enrichment models
            for model_name in ["dependency", "data", "event", "api", "validation", "metrics"]:
                if result.get(model_name) is not None:
                    discovery_summary[model_name] = result[model_name]
        
        # Render presentation IR
        presentation = pipeline.render_presentation(context)
        
        response_content = {
            "repository": repository,
            "language": context.language or "unknown",
            "change_summary": result.get("change", {}),
            "behavior_summary": result.get("behavior", {}),
            "operational_summary": {
                k: v for k, v in result.items()
                if k in ["dependency", "data", "event", "api", "validation", "metrics"]
            },
            "discovery_summary": discovery_summary,
            "timing": {
                "repository": context.repository_compile_time or 0.0,
                "change": context.change_compile_time or 0.0,
                "behavior": context.behavior_compile_time or 0.0,
                "operational": context.operational_compile_time or 0.0,
                "presentation": context.presentation_compile_time or 0.0,
                "total": context.total_time or 0.0,
            },
        }
        
        # Include presentation IR if available
        if presentation is not None:
            response_content["presentation"] = presentation
            
            # Generate LLM comment if presentation IR is available
            try:
                print("[routes] Generating LLM comment")
                llm_result = pipeline.generate_llm_comment(
                    context,
                    repository=repository,
                    pr_number=str(pr_number) if pr_number else "",
                    language=context.language or "unknown",
                )
                # Build LLM context for response
                llm_context_dict = pipeline.build_llm_context(context)
                response_content["llm"] = {
                    "model": llm_result.get("model", "unknown"),
                    "generated": llm_result.get("generated", False),
                    "comment": llm_result.get("comment", ""),
                    "is_valid": llm_result.get("is_valid", False),
                    "validation_errors": llm_result.get("validation_errors", []),
                    "truncated": llm_result.get("truncated", False),
                    "context": llm_context_dict,
                }
                print(f"[routes] LLM comment generated: model={llm_result.get('model')}, valid={llm_result.get('is_valid')}")
            except Exception as exc:
                print(f"[routes] LLM comment generation failed: {exc}")
                # Include error in response but don't fail the request
                response_content["llm"] = {
                    "model": "error",
                    "generated": False,
                    "comment": "## ⚠️ Analysis Complete\n\nFactor analysis completed. LLM comment generation failed.",
                    "is_valid": False,
                    "validation_errors": [str(exc)],
                    "truncated": False,
                    "context": None,
                }
        
        return JSONResponse(
            content=response_content,
            status_code=200,
        )
    
    except PipelineExecutionError as exc:
        print(f"[routes] PipelineExecutionError: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[routes] Unexpected error: {exc}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


def _get_github_token() -> str | None:
    """Get a GitHub token for API authentication.
    
    Prefers PAT from settings, falls back to generating a JWT from the app.
    Note: JWT tokens only work for app-level endpoints, not repository content.
    
    Returns:
        Token string or None
    """
    from api.settings import get_settings
    settings = get_settings()
    return settings.GITHUB_ACCESS_TOKEN


async def _fetch_pr_details_from_url(pr_url: str) -> dict[str, Any]:
    """
    Fetch PR details from GitHub API using a PR URL.
    
    Args:
        pr_url: GitHub PR URL (e.g., "https://github.com/owner/repo/pull/123")
    
    Returns:
        Dictionary with repository, pr_number, base_sha, and head_sha
    
    Raises:
        HTTPException: If URL is invalid or PR details cannot be fetched
    """
    # Parse GitHub PR URL
    pattern = r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.match(pattern, pr_url)
    
    if not match:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid GitHub PR URL format: {pr_url}. Expected format: https://github.com/owner/repo/pull/123"
        )
    
    owner = match.group(1)
    repo = match.group(2)
    pr_number = int(match.group(3))
    repository = f"{owner}/{repo}"
    
    # Fetch PR details from GitHub API with token if available
    token = _get_github_token()
    client = GitHubClient(token=token)
    try:
        response = client.get(
            f"/repos/{repository}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=30,
        )
        response.raise_for_status()
        
        pr_data = response.json()
        
        return {
            "repository": repository,
            "pr_number": pr_number,
            "base_sha": pr_data.get("base", {}).get("sha"),
            "head_sha": pr_data.get("head", {}).get("sha"),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch PR details from GitHub: {exc}"
        ) from exc
    finally:
        client.close()


async def _process_pr_analysis(
    request: AnalysisRequest,
    installation_id: int | None,
    delivery_id: str | None,
) -> None:
    """
    Background task to process PR analysis.
    
    Executes the analysis pipeline for a pull request and publishes the results
    as a comment on the PR using the GitHub integration output provider.
    
    Args:
        request (AnalysisRequest): The analysis request containing repository,
            pull request, and diff information
        installation_id (int | None): GitHub App installation ID used for
            authentication when posting results. Required for private repositories.
        delivery_id (str | None): GitHub webhook delivery ID for tracking
            and debugging purposes
    
    Returns:
        None
    
    Side Effects:
        - Executes the full analysis pipeline (repository, change, behavior, operational)
        - Generates LLM comment from presentation IR
        - Posts analysis results as a comment on the pull request
        - Prints status messages to stdout for logging
    
    Notes:
        - This function runs asynchronously in the background
        - Errors are caught and logged but do not fail the webhook
        - Requires valid GitHub App installation token for posting results
        - Analysis results include change summary, behavior summary, and operational summary
        - LLM comment is generated from presentation IR when available
    """
    pipeline = get_pipeline_instance()
    registry = get_registry_instance()
    
    try:
        # Run pipeline
        context = await pipeline.run(request)
        
        if context.error:
            print(f"Pipeline failed for {request.repository.full_name}: {context.error}")
            return
        
        # Get authentication token if needed
        destination = {
            "repo": request.repository.full_name,
            "pr_number": str(request.pull_request.number) if request.pull_request else None,
            "base_sha": request.pull_request.base_sha if request.pull_request else "",
            "head_sha": request.pull_request.head_sha if request.pull_request else "",
            "language": context.language or "unknown",
            "total_time": f"{context.total_time:.2f}" if context.total_time else "N/A",
        }
        
        if installation_id:
            installation_provider = registry.get_installation_provider("github")
            token = await installation_provider.authenticate(str(installation_id))
            destination["token"] = token
        
        # Try to generate LLM comment from presentation IR
        llm_comment = None
        if context.presentation_ir is not None:
            try:
                print(f"[_process_pr_analysis] Generating LLM comment for {request.repository.full_name}")
                llm_result = pipeline.generate_llm_comment(
                    context,
                    repository=request.repository.full_name,
                    pr_number=str(request.pull_request.number) if request.pull_request else "",
                    language=context.language or "unknown",
                )
                llm_comment = llm_result.get("comment")
                if llm_comment:
                    print(f"[_process_pr_analysis] LLM comment generated: model={llm_result.get('model')}, valid={llm_result.get('is_valid')}")
            except Exception as exc:
                print(f"[_process_pr_analysis] LLM comment generation failed: {exc}")
                # Continue with fallback
        
        # Publish output using output provider
        output_provider = registry.get_output_provider("github")
        
        # Pass LLM comment in destination if available
        if llm_comment:
            destination["llm_comment"] = llm_comment
        
        await output_provider.publish(context.ocm, destination)
        
        print(f"Successfully analyzed {request.repository.full_name}")
    
    except Exception as exc:
        # Log error but don't fail the webhook
        print(f"Error processing PR analysis for {request.repository.full_name}: {exc}")
        import traceback
        traceback.print_exc()
