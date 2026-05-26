"""Worker entrypoint for pull request analysis."""

from __future__ import annotations

import asyncio
import traceback
from time import perf_counter
from typing import Any

from api.settings import get_settings
from api.models import persist_analysis_job
from core_engine.failure_simulation_llm import FailureSimulationLLM
from core_engine.orchestrator import Orchestrator
from source_adapters.github.auth import get_installation_token
from source_adapters.github.comment_formatter import render_pull_request_comment
from source_adapters.github.event_handler import PullRequestAnalysisJob
from source_adapters.github.github_client import build_github_clients
from language_adapters import PythonAdapter
from schemas import AnalyzeRequest


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


def process_pull_request_job(job: PullRequestAnalysisJob) -> dict[str, Any]:
    settings = get_settings()

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

    asyncio.run(
        persist_analysis_job(
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

        asyncio.run(
            persist_analysis_job(
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
        )

        try:
            # Persist analysis run for traceability; do not fail the worker if persistence errors occur
            asyncio.run(orchestrator.log_run(result))
        except Exception as exc:
            print(f"Failed to persist analysis run from worker: {repr(exc)}")

        return result
    except Exception as exc:
        asyncio.run(
            persist_analysis_job(
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
        )
        raise
