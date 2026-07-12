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
from core_engine.pipelines.compiler import Compiler
from core_engine.pipelines.registry import PassRegistry
from core_engine.analyzers.execution_analyzer import ExecutionAnalyzer
from core_engine.analyzers.interaction_analyzer import InteractionAnalyzer
from core_engine.analyzers.propagation_analyzer import PropagationAnalyzer
from core_engine.analyzers.coverage_analyzer import CoverageAnalyzerPass
from core_engine.analyzers.surface_analyzer import SurfaceAnalyzer
from core_engine.analyzers.evidence_collector import EvidenceCollector
from core_engine.analyzers.signal_detector import SignalDetector
from core_engine.analyzers.context_builder import ContextBuilder
from core_engine.analyzers.explainability_auditor import ExplainabilityAuditor
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
    print("BROKER LOADED", broker)
except Exception as e:
    print("BROKER FAILED", repr(e))
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


def build_core_pipeline() -> Compiler:
    """Build the core analysis pipeline."""
    registry = PassRegistry()
    
    # Register all passes in dependency order
    registry.register(ExecutionAnalyzer)
    registry.register(InteractionAnalyzer)
    registry.register(PropagationAnalyzer)
    registry.register(CoverageAnalyzerPass)
    registry.register(SurfaceAnalyzer)
    registry.register(EvidenceCollector)
    registry.register(SignalDetector)
    registry.register(ContextBuilder)
    registry.register(ExplainabilityAuditor)
    
    return Compiler(registry)


async def _process_pull_request_job_async(
    job: PullRequestAnalysisJob,
) -> dict[str, Any]:
    settings = get_settings()
    await _ensure_tortoise_initialized()

    if not job.installation_id:
        raise ValueError("Installation ID is required for GitHub App webhook analysis")

    if not settings.github_app_client_id:
        raise ValueError(
            "GITHUB_APP_CLIENT_ID is required for installation token exchange"
        )

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
        # Build semantic graph from diff
        language = PythonAdapter()
        diff = await source.get_diff(job.full_name, job.pr_number)
        semantic_graph = language.analyze(diff)
        
        # Run core pipeline (new compiler pass architecture)
        pipeline = build_core_pipeline()
        knowledge_model, pass_results = pipeline.compile(
            semantic_graph, 
            graph_id=f"pr_{job.full_name}_{job.pr_number}",
            commit_hash=job.head_sha or "unknown"
        )
        
        # Extract ReviewContext from pass_metadata
        context_builder_metadata = knowledge_model.pass_metadata.get("context_builder", {})
        core_engine_output = {
            "knowledge_model": {
                "graph_id": knowledge_model.graph_id,
                "commit_hash": knowledge_model.commit_hash,
                "execution_units": knowledge_model.execution_units,
                "interaction_clusters": knowledge_model.interaction_clusters,
                "propagation_paths": knowledge_model.propagation_paths,
                "coverage": knowledge_model.coverage,
                "evidence": knowledge_model.evidence,
                "signals": knowledge_model.signals,
                "api_changes": knowledge_model.api_changes,
                "event_changes": knowledge_model.event_changes,
                "schema_changes": knowledge_model.schema_changes,
                "migration_changes": knowledge_model.migration_changes,
                "external_service_calls": knowledge_model.external_service_calls,
                "queue_changes": knowledge_model.queue_changes,
                "cache_changes": knowledge_model.cache_changes,
            },
            "statistics": context_builder_metadata.get("statistics", {}),
            "pass_results": [
                {
                    "pass_name": result.pass_name,
                    "success": result.success,
                    "diagnostics": result.diagnostics,
                    "metadata": result.metadata,
                }
                for result in pass_results
            ],
        }
        
        # Convert to result format
        result = {
            "repo": job.full_name,
            "pr_number": job.pr_number,
            "verdict": "needs_review" if knowledge_model.diagnostics else "approved",
            "pr_risk_level": "high" if len(knowledge_model.diagnostics) > 0 else "low",
            "pr_risk_score": 0.8 if len(knowledge_model.diagnostics) > 0 else 0.2,
            "generated_comment": "; ".join(knowledge_model.diagnostics) if knowledge_model.diagnostics else "No issues found",
            "files": [],
            "language_breakdown": {},
            "framework_hints": [],
            "compressed_for_llm": context_builder_metadata.get("raw_facts", []),
            "entry_points_affected": knowledge_model.execution_units,
            "system_impact": knowledge_model.propagation_paths,
            "excluded_files": [],
            "risk_patterns": [],
            "analysis_mode": "full_analysis",
            "core_engine_output": core_engine_output,
            "analysis_context": {
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
            },
        }
        
        # Render and publish comment
        comment = render_pull_request_comment(result)
        result["generated_comment"] = comment
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
            from api.models import persist_analysis_result
            await persist_analysis_result(result)
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
