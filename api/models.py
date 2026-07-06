from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, cast

from api.settings import get_settings
from tortoise import fields, models


class TimestampedFields:
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


class Organization(TimestampedFields, models.Model):
    org_id = fields.IntField(pk=True)
    github_installation_id = fields.BigIntField(null=True, unique=True)
    github_organization_login = fields.CharField(max_length=255, null=True)
    plan = fields.CharField(max_length=64, default="free")
    billing_status = fields.CharField(max_length=64, default="inactive")
    onboarding_status = fields.CharField(max_length=64, default="pending")
    owner_login = fields.CharField(max_length=255, null=True)
    owner_name = fields.CharField(max_length=255, null=True)
    owner_email = fields.CharField(max_length=255, null=True)
    metadata = fields.JSONField(default=dict)

    class Meta(models.Model.Meta):
        table = "organizations"


class Repository(TimestampedFields, models.Model):
    repo_id = fields.IntField(pk=True)
    organization = fields.ForeignKeyField(
        "models.Organization", related_name="repositories", on_delete=fields.CASCADE
    )
    github_repo_id = fields.BigIntField(null=True)
    full_name = fields.CharField(max_length=255, unique=True)
    name = fields.CharField(max_length=255)
    enabled = fields.BooleanField(default=True)
    default_branch = fields.CharField(max_length=255, default="main")
    language_breakdown = fields.JSONField(default=dict)
    framework_hints = fields.JSONField(default=list)
    last_analyzed_pr_number = fields.IntField(null=True)
    last_analyzed_head_sha = fields.CharField(max_length=128, null=True)
    last_analysis_at = fields.DatetimeField(null=True)
    installation_metadata = fields.JSONField(default=dict)

    class Meta(models.Model.Meta):
        table = "repositories"


class PullRequest(TimestampedFields, models.Model):
    pull_request_id = fields.IntField(pk=True)
    repository = fields.ForeignKeyField(
        "models.Repository", related_name="pull_requests", on_delete=fields.CASCADE
    )
    github_pr_id = fields.BigIntField(null=True)
    number = fields.IntField()
    title = fields.CharField(max_length=512, default="")
    author_login = fields.CharField(max_length=255, default="")
    head_sha = fields.CharField(max_length=128, default="")
    base_sha = fields.CharField(max_length=128, default="")
    merge_sha = fields.CharField(max_length=128, null=True)
    state = fields.CharField(max_length=32, default="open")
    merged = fields.BooleanField(default=False)
    changed_files = fields.JSONField(default=list)
    changed_files_count = fields.IntField(default=0)
    factor_verdict = fields.CharField(max_length=64, null=True)
    analysis_version = fields.CharField(max_length=64, null=True)

    class Meta(models.Model.Meta):
        table = "pull_requests"
        unique_together = (("repository", "number"),)


class PullRequestSnapshot(TimestampedFields, models.Model):
    snapshot_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun", related_name="snapshots", on_delete=fields.CASCADE
    )
    pull_request = fields.ForeignKeyField(
        "models.PullRequest", related_name="snapshots", on_delete=fields.CASCADE
    )
    snapshot_kind = fields.CharField(max_length=64, default="analysis_input")
    head_sha = fields.CharField(max_length=128, default="")
    base_sha = fields.CharField(max_length=128, default="")
    title = fields.CharField(max_length=512, default="")
    author_login = fields.CharField(max_length=255, default="")
    state = fields.CharField(max_length=32, default="")
    merged = fields.BooleanField(default=False)
    changed_files = fields.JSONField(default=list)
    raw_payload = fields.JSONField(default=dict)

    class Meta(models.Model.Meta):
        table = "pull_request_snapshots"


class AnalysisRun(TimestampedFields, models.Model):
    analysis_run_id = fields.IntField(pk=True)
    pull_request = fields.ForeignKeyField(
        "models.PullRequest", related_name="analysis_runs", on_delete=fields.CASCADE
    )
    # Head SHA captured at run time for idempotency and traceability
    head_sha = fields.CharField(max_length=128, default="")
    analyzer_version = fields.CharField(max_length=64)
    reasoning_model_version = fields.CharField(max_length=128)
    execution_duration_ms = fields.IntField(null=True)
    # Lifecycle status: queued, cloning, graph_building, deterministic_analysis,
    # reasoning, comment_generation, posting, completed, failed, partially_failed
    status = fields.CharField(max_length=32, default="completed")
    triggered_by = fields.CharField(max_length=64, default="pull_request")
    webhook_action = fields.CharField(max_length=32, null=True)
    # Delivery ID from webhook — used for deduplication. Should be unique when present.
    delivery_id = fields.CharField(max_length=128, null=True, unique=True)
    # Failure and retry metadata
    failure_stage = fields.CharField(max_length=64, null=True)
    failure_trace = fields.TextField(null=True)
    retry_count = fields.IntField(default=0)
    partial_artifacts = fields.JSONField(default=list)
    risk_score = fields.FloatField(null=True)
    risk_category = fields.CharField(max_length=64, default="")
    verdict = fields.CharField(max_length=64, default="")
    # Canonical comment should live in AnalysisComment — this field stores a short
    # summary or reference to the canonical comment for quick searching.
    generated_comment_summary = fields.TextField(null=True)
    # Reference to the canonical comment (AnalysisComment) when posted.
    canonical_comment = fields.ForeignKeyField(
        "models.AnalysisComment",
        related_name="canonical_for_run",
        null=True,
        on_delete=fields.SET_NULL,
    )
    analysis_mode = fields.CharField(max_length=32, default="")
    analysis_snapshot = fields.JSONField(default=dict)
    internal_reasoning_artifacts = fields.JSONField(default=dict)
    # Schema / format versioning to support replayability across analyzer changes
    graph_schema_version = fields.CharField(max_length=64, null=True)
    finding_schema_version = fields.CharField(max_length=64, null=True)
    reasoning_prompt_version = fields.CharField(max_length=128, null=True)
    risk_taxonomy_version = fields.CharField(max_length=64, null=True)

    class Meta(models.Model.Meta):
        table = "analysis_runs"
        # Prevent duplicate runs for the same PR/head/trigger combination
        unique_together = (("pull_request", "head_sha", "triggered_by"),)


class DeterministicAnalyzerOutput(TimestampedFields, models.Model):
    output_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun",
        related_name="deterministic_outputs",
        on_delete=fields.CASCADE,
    )
    files = fields.JSONField(default=list)
    risk_patterns = fields.JSONField(default=list)
    entry_points_affected = fields.JSONField(default=list)
    system_impact = fields.JSONField(default=list)
    excluded_files = fields.JSONField(default=list)
    compressed_for_llm = fields.JSONField(default=dict)
    dependency_graph = fields.JSONField(default=dict)
    # Indexed metadata extracted from dependency_graph / execution paths for queryability
    node_count = fields.IntField(null=True)
    edge_count = fields.IntField(null=True)
    impacted_auth_nodes_count = fields.IntField(null=True)
    service_boundary_count = fields.IntField(null=True)
    impacted_services = fields.JSONField(default=list)
    auth_boundary_changes = fields.JSONField(default=list)
    dataflow_changes = fields.JSONField(default=list)
    deleted_guards = fields.JSONField(default=list)
    changed_api_contracts = fields.JSONField(default=list)
    event_flow_modifications = fields.JSONField(default=list)
    inferred_risk_regions = fields.JSONField(default=list)

    class Meta(models.Model.Meta):
        table = "deterministic_analyzer_outputs"


class AnalysisJob(TimestampedFields, models.Model):
    """Queue/job entity separate from AnalysisRun for leasing, retries, and scheduling."""

    job_id = fields.IntField(pk=True)
    repo_full_name = fields.CharField(max_length=255)
    owner_login = fields.CharField(max_length=255, null=True)
    repo_name = fields.CharField(max_length=255, null=True)
    pr_number = fields.IntField()
    head_sha = fields.CharField(max_length=128, null=True)
    base_sha = fields.CharField(max_length=128, null=True)
    action = fields.CharField(max_length=64)
    installation_id = fields.BigIntField(null=True)
    payload_json = fields.JSONField(default=dict)
    result_summary = fields.JSONField(default=dict)
    error_stage = fields.CharField(max_length=64, null=True)
    error_trace = fields.TextField(null=True)
    pull_request = fields.ForeignKeyField(
        "models.PullRequest", related_name="jobs", null=True, on_delete=fields.SET_NULL
    )
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun",
        related_name="job_record",
        null=True,
        on_delete=fields.SET_NULL,
    )
    status = fields.CharField(max_length=32, default="queued")
    attempts = fields.IntField(default=0)
    max_attempts = fields.IntField(default=5)
    priority = fields.IntField(default=50)
    lease_owner = fields.CharField(max_length=255, null=True)
    lease_expires_at = fields.DatetimeField(null=True)
    next_retry_at = fields.DatetimeField(null=True)
    idempotency_key = fields.CharField(max_length=128, null=True, unique=True)
    delivery_id = fields.CharField(max_length=128, null=True)

    class Meta(models.Model.Meta):
        table = "analysis_jobs"


class RiskFinding(TimestampedFields, models.Model):
    finding_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun", related_name="risk_findings", on_delete=fields.CASCADE
    )
    category = fields.CharField(max_length=128)
    severity = fields.CharField(max_length=32)
    confidence_bucket = fields.CharField(max_length=32)
    confidence = fields.FloatField(null=True)
    evidence = fields.JSONField(default=dict)
    affected_components = fields.JSONField(default=list)
    code_locations = fields.JSONField(default=list)
    summary = fields.TextField(default="")

    class Meta(models.Model.Meta):
        table = "risk_findings"


class AnalysisArtifact(TimestampedFields, models.Model):
    artifact_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun", related_name="artifacts", on_delete=fields.CASCADE
    )
    artifact_type = fields.CharField(max_length=64)
    storage_uri = fields.CharField(max_length=512, null=True)
    checksum = fields.CharField(max_length=128, null=True)
    mime_type = fields.CharField(max_length=128, null=True)
    size_bytes = fields.BigIntField(null=True)
    payload_json = fields.JSONField(null=True)
    metadata = fields.JSONField(default=dict)

    class Meta(models.Model.Meta):
        table = "analysis_artifacts"


class AnalysisComment(TimestampedFields, models.Model):
    comment_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun", related_name="comments", on_delete=fields.CASCADE
    )
    body = fields.TextField()
    comment_type = fields.CharField(max_length=32, default="initial")
    suppressed = fields.BooleanField(default=False)
    human_overridden = fields.BooleanField(default=False)
    reactions = fields.JSONField(default=dict)
    github_comment_id = fields.BigIntField(null=True)
    posted_at = fields.DatetimeField(null=True)

    class Meta(models.Model.Meta):
        table = "analysis_comments"


class FeedbackSignal(TimestampedFields, models.Model):
    feedback_signal_id = fields.IntField(pk=True)
    analysis_run = fields.ForeignKeyField(
        "models.AnalysisRun",
        related_name="feedback_signals",
        null=True,
        on_delete=fields.SET_NULL,
    )
    pull_request = fields.ForeignKeyField(
        "models.PullRequest", related_name="feedback_signals", on_delete=fields.CASCADE
    )
    signal_type = fields.CharField(max_length=64)
    value = fields.BooleanField(null=True)
    source = fields.CharField(max_length=64, default="manual")
    details = fields.JSONField(default=dict)
    observed_at = fields.DatetimeField(auto_now_add=True)

    class Meta(models.Model.Meta):
        table = "feedback_signals"


class EvaluationCase(TimestampedFields, models.Model):
    evaluation_case_id = fields.IntField(pk=True)
    slug = fields.CharField(max_length=255, unique=True)
    case_type = fields.CharField(max_length=64)
    source_repo = fields.CharField(max_length=255, null=True)
    source_pr_number = fields.IntField(null=True)
    expected_verdict = fields.CharField(max_length=64, null=True)
    expected_findings = fields.JSONField(default=list)
    historical_misses = fields.JSONField(default=list)
    tags = fields.JSONField(default=list)
    notes = fields.TextField(default="")

    class Meta(models.Model.Meta):
        table = "evaluation_cases"


# Legacy AnalysisRecord removed — use AnalysisRun, AnalysisArtifact, DeterministicAnalyzerOutput, and RiskFinding instead.


def _jsonable(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())

    if is_dataclass(value):
        return _jsonable(asdict(cast(Any, value)))

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_jsonable(item) for item in value]

    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]

    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=str)]

    return value


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_repo_full_name(repo_full_name: str) -> tuple[str, str]:
    if "/" in repo_full_name:
        owner, name = repo_full_name.split("/", 1)
        return owner, name
    return repo_full_name, repo_full_name


def _confidence_bucket(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


# def _severity_for_category(category: str) -> str:
#     category_upper = category.upper()
#     if category_upper in {
#         RiskEventType.BACKDOOR_INTRODUCED.value,
#         RiskEventType.AUTH_BYPASS.value,
#         RiskEventType.DATA_LEAK_RISK.value,
#     }:
#         return "CRITICAL"
#     if category_upper in {
#         RiskEventType.VALIDATION_REMOVED.value,
#         RiskEventType.CRITICAL_DEPENDENCY_CHANGED.value,
#         RiskEventType.FINANCIAL_LOGIC_CHANGE.value,
#         RiskEventType.FINANCIAL_DATA_MODEL_CHANGE.value,
#     }:
#         return "HIGH"
#     if category_upper in {
#         RiskEventType.TAX_CALCULATION_CHANGE.value,
#         RiskEventType.SCHEMA_MIGRATION.value,
#         RiskEventType.DATA_BACKFILL.value,
#         RiskEventType.STATE_INCONSISTENCY.value,
#         RiskEventType.PERMISSION_REMOVED.value,
#     }:
#         return "MEDIUM"
#     return "MEDIUM"


async def persist_analysis_result(result: dict[str, Any]) -> None:
    settings = get_settings()
    context = result.get("analysis_context") or {}

    repo_full_name = str(result.get("repo", "")).strip()
    if not repo_full_name:
        return

    owner_login, repo_name = _split_repo_full_name(repo_full_name)
    installation_id = _to_int(context.get("installation_id"))
    pr_number = _to_int(result.get("pr_number"))
    if pr_number is None:
        return

    organization_defaults: dict[str, Any] = {
        "github_organization_login": owner_login or None,
        "plan": "free",
        "billing_status": "inactive",
        "onboarding_status": "pending",
        "owner_login": owner_login or None,
        "owner_name": context.get("owner_name"),
        "owner_email": context.get("owner_email"),
        "metadata": {
            "triggered_by": context.get("triggered_by"),
            "delivery_id": context.get("delivery_id"),
        },
    }

    if installation_id is not None:
        organization_defaults["github_installation_id"] = installation_id
        organization, _ = await Organization.update_or_create(
            github_installation_id=installation_id,
            defaults=organization_defaults,
        )
    else:
        organization, _ = await Organization.update_or_create(
            github_organization_login=owner_login or repo_name,
            defaults=organization_defaults,
        )

    repository_defaults: dict[str, Any] = {
        "organization": organization,
        "github_repo_id": _to_int(context.get("repository_id")),
        "name": repo_name,
        "enabled": True,
        "default_branch": context.get("default_branch") or "main",
        "language_breakdown": _jsonable(result.get("language_breakdown", {})) or {},
        "framework_hints": _jsonable(result.get("framework_hints", [])) or [],
        "last_analyzed_pr_number": pr_number,
        "last_analyzed_head_sha": context.get("head_sha") or "",
        "last_analysis_at": datetime.now(timezone.utc),
        "installation_metadata": {
            "installation_id": installation_id,
            "delivery_id": context.get("delivery_id"),
            "triggered_by": context.get("triggered_by"),
        },
    }
    repository, _ = await Repository.update_or_create(
        full_name=repo_full_name,
        defaults=repository_defaults,
    )

    changed_files = _jsonable(result.get("files", [])) or []
    pull_request_defaults: dict[str, Any] = {
        "github_pr_id": _to_int(context.get("pr_id")),
        "title": str(context.get("title") or result.get("title") or ""),
        "author_login": str(context.get("author_login") or ""),
        "head_sha": str(context.get("head_sha") or ""),
        "base_sha": str(context.get("base_sha") or ""),
        "merge_sha": context.get("merge_sha"),
        "state": str(context.get("state") or "open"),
        "merged": bool(context.get("merged", False)),
        "changed_files": changed_files,
        "changed_files_count": len(changed_files),
        "factor_verdict": str(result.get("verdict") or ""),
        "analysis_version": settings.app_version or "0.1.0",
    }
    pull_request, _ = await PullRequest.update_or_create(
        repository=repository,
        number=pr_number,
        defaults=pull_request_defaults,
    )

    analysis_snapshot = _jsonable(result) or {}
    compressed_for_llm = _jsonable(result.get("compressed_for_llm", {})) or {}
    internal_reasoning_artifacts = {
        "compressed_for_llm": compressed_for_llm,
        "entry_points_affected": _jsonable(result.get("entry_points_affected", []))
        or [],
        "system_impact": _jsonable(result.get("system_impact", [])) or [],
        "excluded_files": _jsonable(result.get("excluded_files", [])) or [],
    }

    analysis_run_defaults = dict(
        analyzer_version=settings.app_version or "0.1.0",
        reasoning_model_version=settings.llm_model,
        execution_duration_ms=_to_int(context.get("execution_duration_ms")),
        status=str(context.get("status") or "completed"),
        triggered_by=str(context.get("triggered_by") or "pull_request"),
        webhook_action=context.get("webhook_action"),
        delivery_id=context.get("delivery_id"),
        head_sha=str(context.get("head_sha") or pull_request.head_sha or ""),
        risk_score=_to_float(result.get("pr_risk_score")),
        risk_category=str(result.get("pr_risk_level") or ""),
        verdict=str(result.get("verdict") or ""),
        generated_comment_summary=(
            result.get("generated_comment_summary")
            or (
                result.get("generated_comment")
                and (str(result.get("generated_comment"))[:1024])
            )
        ),
        analysis_mode=str(result.get("analysis_mode") or ""),
        analysis_snapshot=analysis_snapshot,
        internal_reasoning_artifacts=internal_reasoning_artifacts,
    )

    analysis_run, created = await AnalysisRun.get_or_create(
        defaults=analysis_run_defaults,
        pull_request=pull_request,
        head_sha=str(context.get("head_sha") or pull_request.head_sha or ""),
        triggered_by=str(context.get("triggered_by") or "pull_request"),
    )

    if not created:
        return

    await PullRequestSnapshot.create(
        analysis_run=analysis_run,
        pull_request=pull_request,
        snapshot_kind="analysis_run",
        head_sha=str(context.get("head_sha") or pull_request.head_sha or ""),
        base_sha=str(context.get("base_sha") or pull_request.base_sha or ""),
        title=str(context.get("title") or pull_request.title or ""),
        author_login=str(
            context.get("author_login") or pull_request.author_login or ""
        ),
        state=str(context.get("state") or pull_request.state or ""),
        merged=bool(context.get("merged", pull_request.merged)),
        changed_files=changed_files,
        raw_payload=analysis_snapshot,
    )

    await AnalysisArtifact.create(
        analysis_run=analysis_run,
        artifact_type="compressed_for_llm",
        storage_uri=None,
        checksum=None,
        mime_type="application/json",
        size_bytes=None,
        payload_json=compressed_for_llm,
        metadata={
            "triggered_by": context.get("triggered_by"),
            "delivery_id": context.get("delivery_id"),
        },
    )

    system_impact = _jsonable(result.get("system_impact", [])) or []
    impacted_services = []
    for item in system_impact:
        if isinstance(item, dict):
            area = item.get("area")
            if area:
                impacted_services.append(str(area))

    # Extract indexed metadata from compressed_for_llm.dependency_graph where possible
    dep_graph = compressed_for_llm.get("dependency_graph", {}) or {}
    nodes = []
    edges = []
    try:
        if isinstance(dep_graph, dict):
            nodes = dep_graph.get("nodes") or dep_graph.get("node_list") or []
            edges = dep_graph.get("edges") or dep_graph.get("links") or []
        elif isinstance(dep_graph, list):
            nodes = dep_graph
            edges = []
    except Exception:
        nodes = []
        edges = []

    node_count = len(nodes) if nodes is not None else None
    edge_count = len(edges) if edges is not None else None

    # Best-effort counts for auth/service boundaries
    impacted_auth_nodes_count = 0
    service_boundary_count = 0
    if nodes:
        for n in nodes:
            if isinstance(n, dict):
                tags = n.get("tags") or []
                ntype = n.get("type") or n.get("node_type")
                if (
                    n.get("auth")
                    or "auth" in tags
                    or (isinstance(ntype, str) and "auth" in ntype.lower())
                ):
                    impacted_auth_nodes_count += 1
                if isinstance(ntype, str) and "service" in ntype.lower():
                    service_boundary_count += 1


    await DeterministicAnalyzerOutput.create(
        analysis_run=analysis_run,
        files=changed_files,
        risk_patterns=_jsonable(result.get("risk_patterns", [])) or [],
        entry_points_affected=_jsonable(result.get("entry_points_affected", [])) or [],
        system_impact=system_impact,
        excluded_files=_jsonable(result.get("excluded_files", [])) or [],
        compressed_for_llm=compressed_for_llm,
        dependency_graph=dep_graph,
        node_count=node_count,
        edge_count=edge_count,
        impacted_auth_nodes_count=impacted_auth_nodes_count,
        service_boundary_count=service_boundary_count,
        impacted_services=impacted_services,
        auth_boundary_changes=compressed_for_llm.get("auth_boundary_changes", []) or [],
        dataflow_changes=compressed_for_llm.get("dataflow_changes", []) or [],
        deleted_guards=compressed_for_llm.get("deleted_guards", []) or [],
        changed_api_contracts=compressed_for_llm.get("changed_api_contracts", []) or [],
        event_flow_modifications=compressed_for_llm.get("event_flow_modifications", [])
        or [],
        inferred_risk_regions=compressed_for_llm.get("inferred_risk_regions", []) or [],
    )

    risk_patterns = _jsonable(result.get("risk_patterns", [])) or []
    for risk in risk_patterns:
        if not isinstance(risk, dict):
            continue
        category = str(risk.get("type") or risk.get("category") or "unknown")
        confidence = _to_float(risk.get("confidence"))
        system_areas = risk.get("system_areas") or []
        code_locations = [
            {
                "file_path": risk.get("file_path"),
                "function": risk.get("function"),
                "trigger": risk.get("trigger"),
                "reason": risk.get("reason"),
            }
        ]
        await RiskFinding.create(
            analysis_run=analysis_run,
            category=category,
            # severity=_severity_for_category(category),
            confidence_bucket=_confidence_bucket(confidence),
            confidence=confidence,
            evidence={
                "trigger": risk.get("trigger"),
                "reason": risk.get("reason"),
                "flows": risk.get("flows"),
                "system_areas": system_areas,
            },
            affected_components=[
                str(item) for item in system_areas if str(item).strip()
            ],
            code_locations=code_locations,
            summary=str(risk.get("reason") or risk.get("trigger") or category),
        )

    # Create canonical AnalysisComment if analyzer produced a comment body.
    generated_body = None
    if isinstance(result.get("generated_comment"), (str,)) and result.get(
        "generated_comment"
    ):
        generated_body = result.get("generated_comment")
    elif isinstance(
        analysis_snapshot.get("generated_comment"), (str,)
    ) and analysis_snapshot.get("generated_comment"):
        generated_body = analysis_snapshot.get("generated_comment")

    if generated_body:
        comment = await AnalysisComment.create(
            analysis_run=analysis_run,
            body=generated_body,
            comment_type="initial",
            suppressed=False,
            human_overridden=False,
            reactions={},
            posted_at=datetime.now(timezone.utc),
        )
        # Link canonical comment back to the run and persist summary
        analysis_run.canonical_comment = comment
        analysis_run.generated_comment_summary = str(generated_body[:1024])
        await analysis_run.save()


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
