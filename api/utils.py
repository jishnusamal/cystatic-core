from fastapi import Header, HTTPException, Request, BackgroundTasks, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from schemas import AnalyzeRequest
import os, json
from .settings import get_settings
from api.models import persist_analysis_job
from source_adapters.github.event_handler import (
    build_pull_request_analysis_job,
    schedule_pull_request_analysis,
    should_process_pull_request_event,
)
from source_adapters.github.webhook import verify_github_webhook_signature
import logging

logger = logging.getLogger(__name__)

def verify_api_key(x_api_key: str = Header(...)):
    settings = get_settings()
    keys = json.loads(settings.cystatic_keys) if isinstance(settings.cystatic_keys, str) else settings.cystatic_keys
    
    if x_api_key not in keys.values():
        raise HTTPException(status_code=401, detail="Invalid API key")
    

async def github_webhook_handler(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
):
    payload_bytes = await request.body()
    settings = get_settings()

    print(
        "GitHub webhook received:",
        {
            "event": x_github_event,
            "delivery": x_github_delivery,
            "content_length": request.headers.get("content-length"),
        },
    )

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
        logger.info("Published job")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        job_record, _ = await persist_analysis_job(
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

    schedule_pull_request_analysis(background_tasks, job, use_queue=settings.use_queue)

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
