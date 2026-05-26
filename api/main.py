from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, APIRouter, Depends, Body, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from tortoise.contrib.fastapi import register_tortoise

# Internal imports
from schemas import AnalyzeRequest
from api.utils import verify_api_key
from api.settings import get_settings
from source_adapters.github.event_handler import (
    build_pull_request_analysis_job,
    schedule_pull_request_analysis,
    should_process_pull_request_event,
)
from source_adapters.github.webhook import verify_github_webhook_signature
from source_adapters.github import GitHubSource, GitHubPublisher
from source_adapters.github.auth import get_installation_token
from source_adapters.github.github_client import build_github_clients
from api.models import persist_analysis_job
from language_adapters import PythonAdapter
from core_engine.orchestrator import Orchestrator, DiffOrchestrator
from core_engine.failure_simulation_llm import FailureSimulationLLM
from api.db import TORTOISE_ORM
from instrumentation import sentry, sentry_pr_context

settings = get_settings()
app = FastAPI(title="Cystatic", version=settings.app_version or "0.1.0")
sentry.attach_middleware(app) 
router = APIRouter(prefix="/v1")


def build_failure_simulation_llm() -> FailureSimulationLLM | None:
    api_key = settings.llm_api_key or settings.ai_api_key
    
    print("LLM api key exists:", bool(api_key))
    print("LLM model:", settings.llm_model)
    print("LLM base url:", settings.llm_base_url)

    if not api_key:
        return None

    return FailureSimulationLLM(
        api_key=api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        site_url=settings.llm_base_url,
        site_name=settings.llm_base_url,
    )

@app.api_route(
    "/health",
    methods=["GET", "HEAD"],
    dependencies=[Depends(get_settings)],
)
async def health(request: Request):
    if request.method == "HEAD":
        return Response(status_code=status.HTTP_200_OK)
    return {"status": "ok"}

@router.post("/analyze-pr", dependencies=[
        Depends(verify_api_key),
        Depends(sentry_pr_context),
    ])
async def analyze_pr(body: AnalyzeRequest = Body(...)):
    if not body.installation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="installation_id is required for GitHub App authentication"
        )
    
    if not settings.github_app_client_id or not settings.github_private_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub App is not configured"
        )
    
    token = get_installation_token(
        app_id=settings.github_app_client_id,
        private_key=settings.github_private_key,
        installation_id=body.installation_id,
    )
    
    source, publisher = build_github_clients(token)
    
    failure_simulation_llm = build_failure_simulation_llm()
    orchestrator = Orchestrator(
        request=body,
        source=source,
        language=PythonAdapter(),
        publisher=publisher,
        failure_simulation_llm=failure_simulation_llm,
    )
    result = orchestrator.run_pr_analysis()
    orchestrator.publish_comments(result)

    if settings.app_env == "production":
        await orchestrator.log_run(result)
    return result

@router.post("/analyze-diff")
async def analyze_diff(body: str = Body(..., media_type="text/plain")):
    diff_text = body
    # print(f"Received diff for analysis:\n{diff_text[:500]}...")  # Log the first 500 chars of the diff

    failure_simulation_llm = build_failure_simulation_llm()
    # For diff analysis, we don't need GitHub API access, just diff parsing
    orchestrator = DiffOrchestrator(
        request={
            "diff": diff_text
        },  
        source=GitHubSource(token=None),  # No GitHub API needed for pure diff analysis
        language=PythonAdapter(),
        failure_simulation_llm=failure_simulation_llm,
    )

    result = orchestrator.run_pr_analysis()

    if settings.app_env == "production":
        await orchestrator.log_run(result)
    
    return orchestrator.publish_comments(result)


@app.post("/github/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
):
    payload_bytes = await request.body()

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc

    if not verify_github_webhook_signature(
        payload=payload_bytes,
        signature=x_hub_signature_256,
        secret=settings.github_app_webhook_secret,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub signature")

    action = payload.get("action") if isinstance(payload, dict) else None
    if not should_process_pull_request_event(x_github_event, action):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ignored",
                "event": x_github_event,
                "action": action,
                "delivery_id": x_github_delivery,
            },
        )

    try:
        job = build_pull_request_analysis_job(payload, delivery_id=x_github_delivery)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Persist job record for tracking and idempotency
    try:
        job_record, created = await persist_analysis_job(
            repo_full_name=job.full_name,
            pr_number=job.pr_number,
            action=job.action,
            installation_id=job.installation_id,
            delivery_id=job.delivery_id,
            head_sha=job.head_sha,
            base_sha=job.base_sha,
            owner_login=job.owner,
            repo_name=job.repo,
            payload_json=payload,
        )
    except Exception:
        job_record = None

    schedule_pull_request_analysis(background_tasks, job)

    # Include persisted job id in the response when available
    job_id_value = None
    if job_record is not None:
        job_id_value = getattr(job_record, "job_id", None) or getattr(job_record, "id", None)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "accepted",
            "installation_id": job.installation_id,
            "owner": job.owner,
            "repo": job.repo,
            "pr_number": job.pr_number,
            "action": job.action,
            "delivery_id": x_github_delivery,
            "job_id": job_id_value,
        },
    )

app.include_router(router)

register_tortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=False,
    add_exception_handlers=True,
)