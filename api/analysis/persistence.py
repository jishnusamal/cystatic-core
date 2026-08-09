from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.models import (
    AnalysisArtifact,
    AnalysisComment,
    AnalysisRun,
    DeterministicAnalyzerOutput,
    Organization,
    PullRequest,
    PullRequestSnapshot,
    Repository,
    RiskFinding,
)
from api.settings import get_settings
from .helpers import (
    _confidence_bucket,
    _jsonable,
    _severity_for_category,
    _split_repo_full_name,
    _to_float,
    _to_int,
)


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

    changed_execution_path_count = (
        len(compressed_for_llm.get("execution_paths", []))
        if compressed_for_llm.get("execution_paths") is not None
        else 0
    )

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
        changed_execution_path_count=changed_execution_path_count,
        impacted_services=impacted_services,
        execution_paths=compressed_for_llm.get("execution_paths", []) or [],
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
            severity=_severity_for_category(category),
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
            inferred_blast_radius=[
                str(item) for item in system_impact if str(item).strip()
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
