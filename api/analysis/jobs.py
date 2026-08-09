from __future__ import annotations

from datetime import datetime
from typing import Any

from api.models import AnalysisJob
from .helpers import _split_repo_full_name


async def persist_analysis_job(
    *,
    repo_full_name: str,
    pr_number: int,
    action: str,
    installation_id: int | None = None,
    delivery_id: str | None = None,
    head_sha: str | None = None,
    base_sha: str | None = None,
    owner_login: str | None = None,
    repo_name: str | None = None,
    payload_json: dict[str, Any] | None = None,
    status: str = "queued",
    attempts: int = 0,
    max_attempts: int = 5,
    priority: int = 50,
    result_summary: dict[str, Any] | None = None,
    error_stage: str | None = None,
    error_trace: str | None = None,
    lease_owner: str | None = None,
    lease_expires_at: datetime | None = None,
    next_retry_at: datetime | None = None,
) -> tuple[AnalysisJob, bool]:
    if not owner_login or not repo_name:
        owner_login, repo_name = _split_repo_full_name(repo_full_name)

    idempotency_key = (
        delivery_id or f"{repo_full_name}:{pr_number}:{head_sha or ''}:{action}"
    )

    defaults: dict[str, Any] = {
        "repo_full_name": repo_full_name,
        "owner_login": owner_login,
        "repo_name": repo_name,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "action": action,
        "installation_id": installation_id,
        "payload_json": payload_json or {},
        "result_summary": result_summary or {},
        "error_stage": error_stage,
        "error_trace": error_trace,
        "status": status,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "priority": priority,
        "lease_owner": lease_owner,
        "lease_expires_at": lease_expires_at,
        "next_retry_at": next_retry_at,
        "delivery_id": delivery_id,
    }

    job, created = await AnalysisJob.update_or_create(
        idempotency_key=idempotency_key,
        defaults=defaults,
    )
    return job, created
