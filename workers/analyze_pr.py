"""Worker entrypoint for pull request analysis."""

from __future__ import annotations

import asyncio
import traceback
from time import perf_counter
from typing import Any

import dramatiq
from api.db import TORTOISE_ORM
from api.models import persist_analysis_job
from api.settings import get_settings
from core_engine.failure_simulation_llm import FailureSimulationLLM
from core_engine.orchestrator import Orchestrator
from language_adapters import PythonAdapter
from schemas import AnalyzeRequest
from source_adapters.github.auth import get_installation_token
from source_adapters.github.comment_formatter import render_pull_request_comment
from source_adapters.github.event_handler import PullRequestAnalysisJob
from source_adapters.github.github_client import build_github_clients
from tortoise import Tortoise

try:
    from workers.queue import broker

    dramatiq.set_broker(broker)
except Exception:
    broker = None

actor = dramatiq.actor


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _ensure_tortoise_initialized() -> None:
    if not Tortoise.is_inited():
        await Tortoise.init(config=TORTOISE_ORM)


def build_failure_simulation_llm() -> FailureSimulationLLM | None:
    settings = get_settings()
    api_key = settings.llm_api_key or settings.ai_api_key

    if not api_key:
        return None

    return FailureSimulationLLM(
        api_key=api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        site_url=settings.llm_base_url,
        site_name=settings.llm_base_url,
    )


async def _process_pull_request_job_async(job: PullRequestAnalysisJob) -> dict[str, Any]:
    settings = get_settings()
    await _ensure_tortoise_initialized()

    if not job.installation_id:
        raise ValueError("Installation ID is required for GitHub App webhook analysis")

    if not settings.github_app_client_id:
        raise ValueError("GITHUB_APP_CLIENT_ID is required for installation token exchange")

    token = get_installation_token(
        app_id=settings.github_app_client_id,
        private_key=settings.github_private_key,
        installation_id=job.installation_id,
    )
    source, publisher = build_github_clients(token)

    await persist_analysis_job(
        repo_full_name=job.full_name,
        pr_number=job.pr_number,
        action=job.action,
        installation_id=job.installation_id,
        delivery_id=job.delivery_id,
        head_sha=job.head_sha,
        base_sha=job.base_sha,
        owner_login=job.owner,
        repo_name=job.repo,
        payload_json={
            "phase": "started",
            "installation_id": job.installation_id,
        },
        status="running",
        attempts=1,
        result_summary={"phase": "running"},
    )

    started_at = perf_counter()
    try:
        orchestrator = Orchestrator(
            request=AnalyzeRequest(repo=job.full_name, pr_number=job.pr_number),
            source=source,
            language=PythonAdapter(),
            publisher=publisher,
            failure_simulation_llm=build_failure_simulation_llm(),
        )

        result = orchestrator.run_pr_analysis()
        comment = render_pull_request_comment(result)
        result["generated_comment"] = comment
        result["analysis_context"] = {
            "installation_id": job.installation_id,
            "delivery_id": job.delivery_id,
            "triggered_by": job.action,
            "webhook_action": job.action,
            "head_sha": job.head_sha,
            "base_sha": job.base_sha,
            "title": job.title,
            "author_login": job.author_login,
            "merge_sha": job.merge_sha,
            "state": job.state,
            "merged": job.merged,
            "changed_files_count": job.changed_files_count,
            "repository_id": job.repository_id,
            "pr_id": job.github_pr_id,
            "default_branch": job.default_branch,
            "execution_duration_ms": int((perf_counter() - started_at) * 1000),
            "status": "completed",
        }
        publisher.post_comment(job.full_name, job.pr_number, comment)

        await persist_analysis_job(
            repo_full_name=job.full_name,
            pr_number=job.pr_number,
            action=job.action,
            installation_id=job.installation_id,
            delivery_id=job.delivery_id,
            head_sha=job.head_sha,
            base_sha=job.base_sha,
            owner_login=job.owner,
            repo_name=job.repo,
            payload_json={"phase": "completed"},
            status="completed",
            attempts=1,
            result_summary={
                "phase": "completed",
                "verdict": result.get("verdict"),
                "risk_level": result.get("pr_risk_level"),
            },
        )

        try:
            await orchestrator.log_run(result)
        except Exception as exc:
            print(f"Failed to persist analysis run from worker: {repr(exc)}")

        return result
    except Exception as exc:
        await persist_analysis_job(
            repo_full_name=job.full_name,
            pr_number=job.pr_number,
            action=job.action,
            installation_id=job.installation_id,
            delivery_id=job.delivery_id,
            head_sha=job.head_sha,
            base_sha=job.base_sha,
            owner_login=job.owner,
            repo_name=job.repo,
            payload_json={"phase": "failed"},
            status="failed",
            attempts=1,
            error_stage="worker",
            error_trace=traceback.format_exc(),
            result_summary={"phase": "failed", "error": repr(exc)},
        )
        raise


def process_pull_request_job(job: PullRequestAnalysisJob) -> dict[str, Any]:
    return asyncio.run(_process_pull_request_job_async(job))


@actor(queue_name="analysis_jobs", max_retries=0)
def process_pull_request_job_actor(job_dict: dict) -> None:
    pj = PullRequestAnalysisJob(
        installation_id=_optional_int(job_dict.get("installation_id")),
        owner=str(job_dict.get("owner") or ""),
        repo=str(job_dict.get("repo") or ""),
        pr_number=int(job_dict.get("pr_number") or 0),
        action=str(job_dict.get("action") or ""),
        delivery_id=job_dict.get("delivery_id"),
        head_sha=job_dict.get("head_sha"),
        base_sha=job_dict.get("base_sha"),
        title=job_dict.get("title"),
        author_login=job_dict.get("author_login"),
        merge_sha=job_dict.get("merge_sha"),
        state=job_dict.get("state"),
        merged=bool(job_dict.get("merged", False)),
        changed_files_count=_optional_int(job_dict.get("changed_files_count")),
        repository_id=job_dict.get("repository_id"),
        github_pr_id=job_dict.get("github_pr_id"),
        default_branch=job_dict.get("default_branch"),
    )
    process_pull_request_job(pj)
