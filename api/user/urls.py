from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import JSONResponse
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
from source_adapters.github import GitHubPublisher, GitHubSource
from source_adapters.github.auth import get_installation_token
from source_adapters.github.github_client import (
    build_github_clients,
    build_public_github_client,
)
from api.utils import github_webhook_handler
from instrumentation import sentry_pr_context

router = APIRouter()
settings = get_settings()


def _render_pr_comment(reasoning_packet) -> str:
    """Render PR comment from reasoning packet."""
    lines = [f"## Analysis Summary\n{reasoning_packet.summary}\n"]
    
    if reasoning_packet.changed_areas:
        lines.append("### Changed Areas")
        lines.extend(f"- {area}" for area in reasoning_packet.changed_areas)
        lines.append("")
    
    if reasoning_packet.migrations:
        lines.append("### Database Migrations")
        lines.extend(f"- {m}" for m in reasoning_packet.migrations)
        lines.append("")
    
    if reasoning_packet.validations:
        lines.append("### Validation Logic")
        lines.extend(f"- {v}" for v in reasoning_packet.validations)
        lines.append("")
    
    if reasoning_packet.persistence:
        lines.append("### Persistence Changes")
        lines.extend(f"- {p}" for p in reasoning_packet.persistence)
        lines.append("")
    
    if reasoning_packet.transactions:
        lines.append("### Transaction Boundaries")
        lines.extend(f"- {t}" for t in reasoning_packet.transactions)
        lines.append("")
    
    if reasoning_packet.queries:
        lines.append("### Database Queries")
        lines.extend(f"- {q}" for q in reasoning_packet.queries)
        lines.append("")
    
    if reasoning_packet.external_calls:
        lines.append("### External API Calls")
        lines.extend(f"- {e}" for e in reasoning_packet.external_calls)
        lines.append("")
    
    if reasoning_packet.tests:
        lines.append("### Test Coverage")
        for test in reasoning_packet.tests:
            lines.append(f"- {test.get('name', 'Unknown')}: {test.get('status', 'unknown')}")
        lines.append("")
    
    if reasoning_packet.unresolved:
        lines.append("### ⚠️ Items Requiring Review")
        lines.extend(f"- {u}" for u in reasoning_packet.unresolved)
        lines.append("")
    
    return "\n".join(lines)


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


def build_behavior_graph_pipeline() -> BehaviorGraphPipeline:
    """Build the behavior graph pipeline (FGCS v2)."""
    return BehaviorGraphPipeline()


@router.post(
    "/v1/analyze-pr",
    dependencies=[Depends(sentry_pr_context)],
)
async def analyze_pr(body: AnalyzeRequest = Body(...)):
    if not body.installation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="installation_id is required for GitHub App authentication",
        )

    if not settings.github_app_client_id or not settings.github_private_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub App is not configured",
        )

    token = get_installation_token(
        app_id=settings.github_app_client_id,
        private_key=settings.github_private_key,
        installation_id=body.installation_id,
    )

    source, publisher = build_github_clients(token)

    # Build semantic graph from diff
    language = PythonAdapter()
    diff = source.fetch_diff(body.repo, body.pr_number)
    file_contents = source.fetch_pr_files(body.repo, body.pr_number)
    semantic_graph = language.analyze(diff, file_contents)
    
    # Run core pipeline (new compiler pass architecture)
    pipeline = build_core_pipeline()
    knowledge_model, pass_results = pipeline.compile(
        semantic_graph, 
        graph_id=f"pr_{body.repo}_{body.pr_number}",
        commit_hash=body.head_sha or "unknown"
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
    
    # Run behavior graph pipeline (FGCS v2 - behavior graph)
    bg_pipeline = build_behavior_graph_pipeline()
    behavior_result = bg_pipeline.run(semantic_graph)
    
    # Convert to result format
    result = {
        "repo": body.repo,
        "pr_number": body.pr_number,
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
        # Core Engine output
        "core_engine_output": core_engine_output,
        # Behavior Graph v2 output
        "behavior_graph": {
            "components": {
                cid: {
                    "id": c.id,
                    "type": c.type.name.title(),
                    "domain": c.domain,
                    "location": c.location,
                    "capabilities": [cap.name for cap in c.capabilities],
                    "responsibilities": [r.name for r in c.responsibilities],
                    "reads": c.reads,
                    "writes": c.writes,
                    "validates": c.validates,
                    "calls": c.calls,
                    "emits": c.emits,
                    "transactions": c.transactions,
                    "tests": c.tests,
                }
                for cid, c in behavior_result.graph.components.items()
            },
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.edge_type.name,
                }
                for e in behavior_result.graph.edges
            ],
            "domains": list(behavior_result.graph.domains.keys()),
            "yaml": behavior_result.graph.to_yaml(),
        },
    }
    
    # Publish comment if publisher available
    if publisher:
        comment = _render_pr_comment(reasoning_packet)
        publisher.post_comment(body.repo, body.pr_number, comment)
        result["generated_comment"] = comment

    try:
        from api.models import persist_analysis_result
        await persist_analysis_result(result)
    except Exception as exc:
        print(f"Failed to persist analysis run: {repr(exc)}")
    return result


@router.post(
    "/v1/public/analyze-pr",
    dependencies=[Depends(sentry_pr_context)],
)
async def analyze_public_pr(body: AnalyzeRequest = Body(...)):
    # For public repos, token is optional - GitHub API allows unauthenticated access to public repos
    # with lower rate limits (60 requests/hour vs 5000 with token)
    token = settings.github_access_token or None
    source = build_public_github_client(token=token)

    try:
        # Build semantic graph from diff
        language = PythonAdapter()
        diff = source.fetch_diff(body.repo, body.pr_number)
        file_contents = source.fetch_pr_files(body.repo, body.pr_number)
        semantic_graph = language.analyze(diff, file_contents)
        
        # Run core pipeline (new compiler pass architecture)
        pipeline = build_core_pipeline()
        knowledge_model, pass_results = pipeline.compile(
            semantic_graph, 
            graph_id=f"pr_{body.repo}_{body.pr_number}",
            commit_hash=body.head_sha or "unknown"
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
        
        # Run behavior graph pipeline (FGCS v2 - behavior graph)
        bg_pipeline = build_behavior_graph_pipeline()
        behavior_result = bg_pipeline.run(semantic_graph)
        
        # Convert to result format
        result = {
            "repo": body.repo,
            "pr_number": body.pr_number,
            # "verdict": "needs_review" if knowledge_model.diagnostics else "approved",
            # "pr_risk_level": "high" if len(knowledge_model.diagnostics) > 0 else "low",
            # "pr_risk_score": 0.8 if len(knowledge_model.diagnostics) > 0 else 0.2,
            "generated_comment": "; ".join(knowledge_model.diagnostics) if knowledge_model.diagnostics else "No issues found",
            "compressed_for_llm": context_builder_metadata.get("raw_facts", []),
            # "entry_points_affected": knowledge_model.execution_units,
            # "system_impact": knowledge_model.propagation_paths,
            # "excluded_files": [],
            # "risk_patterns": [],
            "analysis_mode": "full_analysis",
            # Core Engine output
            "core_engine_output": core_engine_output,
        }
        
        # Render comment but don't publish
        comment = "; ".join(knowledge_model.diagnostics) if knowledge_model.diagnostics else "No issues found"
        result["generated_comment"] = comment
        print(comment)
    except Exception as exc:
        # Provide a helpful error message for common issues
        error_msg = str(exc)
        if "401" in error_msg or "Unauthorized" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Failed to access the repository. This may be a private repository. "
                    "Please use /v1/analyze-pr with an installation_id for private repositories, "
                    "or ensure the repository is public and you have the necessary access token configured."
                ),
            ) from exc
        raise

    return result


@router.post("/v1/analyze-diff")
async def analyze_diff(body: str = Body(..., media_type="text/plain")):
    from schemas import DiffIR
    
    diff_text = body
    diff = DiffIR.parse_raw(diff_text) if isinstance(diff_text, str) else diff_text

    # Build semantic graph from diff
    language = PythonAdapter()
    semantic_graph = language.analyze(diff)
    
    # Run core pipeline (new compiler pass architecture)
    pipeline = build_core_pipeline()
    knowledge_model, pass_results = pipeline.compile(
        semantic_graph, 
        graph_id="diff_analysis",
        commit_hash="unknown"
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
    
    # Run behavior graph pipeline (FGCS v2 - behavior graph)
    bg_pipeline = build_behavior_graph_pipeline()
    behavior_result = bg_pipeline.run(semantic_graph)
    
    # Convert to result format
    result = {
        "verdict": "needs_review" if knowledge_model.diagnostics else "approved",
        "pr_risk_level": "high" if len(knowledge_model.diagnostics) > 0 else "low",
        "pr_risk_score": 0.8 if len(knowledge_model.diagnostics) > 0 else 0.2,
        "generated_comment": "; ".join(knowledge_model.diagnostics) if knowledge_model.diagnostics else "No issues found",
        "compressed_for_llm": context_builder_metadata.get("raw_facts", []),
        "entry_points_affected": knowledge_model.execution_units,
        "system_impact": knowledge_model.propagation_paths,
        "analysis_mode": "diff_only",
        # Core Engine output
        "core_engine_output": core_engine_output,
        # Behavior Graph v2 output
        "behavior_graph": {
            "components": {
                cid: {
                    "id": c.id,
                    "type": c.type.name.title(),
                    "domain": c.domain,
                    "location": c.location,
                    "capabilities": [cap.name for cap in c.capabilities],
                    "responsibilities": [r.name for r in c.responsibilities],
                    "reads": c.reads,
                    "writes": c.writes,
                    "validates": c.validates,
                    "calls": c.calls,
                    "emits": c.emits,
                    "transactions": c.transactions,
                    "tests": c.tests,
                }
                for cid, c in behavior_result.graph.components.items()
            },
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.edge_type.name,
                }
                for e in behavior_result.graph.edges
            ],
            "domains": list(behavior_result.graph.domains.keys()),
            "yaml": behavior_result.graph.to_yaml(),
        },
    }

    try:
        from api.models import persist_analysis_result
        await persist_analysis_result(result)
    except Exception as exc:
        print(f"Failed to persist analysis run: {repr(exc)}")

    return result


@router.post("/github/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
):
    return await github_webhook_handler(
        request=request,
        background_tasks=background_tasks,
        x_github_event=x_github_event,
        x_github_delivery=x_github_delivery,
        x_hub_signature_256=x_hub_signature_256,
    )