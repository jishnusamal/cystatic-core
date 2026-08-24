import asyncio
import json
import os
import sys
import time

# PYTHONPATH=. infisical run -- uv run python benchmark/run_benchmarks.py

# Add workspace root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.routes.github import _fetch_pr_details_from_url
from core.config import get_settings
from core.profile import MemoryProfiler
from engine.pipeline.pipeline import Pipeline
from models.analysis import AnalysisRequest, AnalysisTrigger
from models.core import PullRequestReference, RepositoryReference


def get_view_metrics(view):
    """
    Extract symbol_count, call_edge_count, and ref_edge_count from the RepositoryView.
    Handles base query being SQLiteRepositoryStore or InMemoryRepository.
    """
    if view is None:
        return 0, 0, 0
    base = view.base
    overlay = view.overlay
    
    # 1. Symbols
    base_symbol_ids = set()
    if hasattr(base, "conn"):  # SQLiteRepositoryStore
        if hasattr(base, "repository_id") and base.repository_id is not None:
            repo_id = base.repository_id
            version_id = base.version_id
        else:
            repo_id, version_id = base._get_context()
        cur = base.conn.cursor()
        cur.execute(
            "SELECT id, file_id FROM symbols WHERE repository_id = ? AND version_id = ?",
            (repo_id, version_id)
        )
        base_symbol_ids = {row["id"] for row in cur.fetchall() if row["file_id"] not in overlay.removed_files and row["file_id"] not in overlay.modified_files}
    elif hasattr(base, "_facts"):  # InMemoryRepository
        base_symbol_ids = {s.id for s in base._facts.symbols if s.file_id not in overlay.removed_files and s.file_id not in overlay.modified_files}
        
    active_symbols = (base_symbol_ids - overlay.removed_symbols) | set(overlay.added_symbols.keys())
    symbol_count = len(active_symbols)
    
    # 2. Call Edges
    base_calls = []
    if hasattr(base, "conn"):
        if hasattr(base, "repository_id") and base.repository_id is not None:
            repo_id = base.repository_id
            version_id = base.version_id
        else:
            repo_id, version_id = base._get_context()
        cur = base.conn.cursor()
        cur.execute(
            "SELECT caller_id, callee_id FROM calls WHERE repository_id = ? AND version_id = ?",
            (repo_id, version_id)
        )
        base_calls = [(row["caller_id"], row["callee_id"]) for row in cur.fetchall()]
    elif hasattr(base, "_facts"):
        base_calls = [(c.caller_id, c.callee_id) for c in base._facts.calls]
        
    from engine.repository.facts import Call
    active_calls = set()
    for caller_id, callee_id in base_calls:
        if view._should_skip_base_for_symbol(caller_id) or caller_id not in active_symbols:
            continue
        if view._should_skip_base_for_symbol(callee_id) or callee_id not in active_symbols:
            continue
        call_obj = Call(caller_id=caller_id, callee_id=callee_id)
        if call_obj in overlay.removed_calls:
            continue
        active_calls.add((caller_id, callee_id))
        
    for c in overlay.added_calls:
        active_calls.add((c.caller_id, c.callee_id))
        
    call_edge_count = len(active_calls)
    
    # 3. Reference Edges
    base_refs = []
    if hasattr(base, "conn"):
        if hasattr(base, "repository_id") and base.repository_id is not None:
            repo_id = base.repository_id
            version_id = base.version_id
        else:
            repo_id, version_id = base._get_context()
        cur = base.conn.cursor()
        cur.execute(
            'SELECT source_id, target_id FROM "references" WHERE repository_id = ? AND version_id = ?',
            (repo_id, version_id)
        )
        base_refs = [(row["source_id"], row["target_id"]) for row in cur.fetchall()]
    elif hasattr(base, "_facts"):
        base_refs = [(r.source_id, r.target_id) for r in base._facts.references]
        
    from engine.repository.facts import Reference
    active_refs = set()
    for source_id, target_id in base_refs:
        if view._should_skip_base_for_symbol(source_id) or source_id not in active_symbols:
            continue
        if view._should_skip_base_for_symbol(target_id) or target_id not in active_symbols:
            continue
        ref_obj = Reference(source_id=source_id, target_id=target_id)
        if ref_obj in overlay.removed_references:
            continue
        active_refs.add((source_id, target_id))
        
    for r in overlay.added_references:
        active_refs.add((r.source_id, r.target_id))
        
    ref_edge_count = len(active_refs)
    
    return symbol_count, call_edge_count, ref_edge_count


async def run_pr_analysis_direct(pr_url: str):
    print("\n==================================================")
    print(f"Running direct memory benchmark for: {pr_url}")
    print("==================================================")

    # Enable memory profiling for this benchmark run
    os.environ["MEMORY_PROFILING"] = "true"
    get_settings().MEMORY_PROFILING = True

    # 1. Parse PR URL
    pr_data = await _fetch_pr_details_from_url(pr_url)
    repo_name = pr_data["repository"]
    pr_number = pr_data["pr_number"]
    base_sha = pr_data["base_sha"]
    head_sha = pr_data["head_sha"]

    # Initialize MemoryProfiler (checkpoint: request start)
    import uuid

    analysis_id = str(uuid.uuid4())[:8]
    profiler = MemoryProfiler(analysis_id=analysis_id)
    profiler.log_memory("request start")

    # Build request objects
    repo_ref = RepositoryReference(
        provider="github",
        owner=repo_name.split("/")[0],
        repository=repo_name.split("/")[1],
        default_branch=base_sha or "main",
    )

    pr_ref = PullRequestReference(
        number=pr_number,
        base_sha=base_sha or "main",
        head_sha=head_sha or "main",
        title="",
    )

    analysis_request_obj = AnalysisRequest(
        repository=repo_ref,
        pull_request=pr_ref,
        trigger=AnalysisTrigger.MANUAL,
    )

    # Instantiate pipeline
    from integrations.base.registry import get_registry
    from integrations.github.provider import GitHubIntegration

    registry = get_registry()
    settings = get_settings()
    github_integration = GitHubIntegration(
        app_id=settings.GITHUB_APP_CLIENT_ID,
        private_key=settings.GITHUB_PRIVATE_KEY,
        client_secret=settings.GITHUB_CLIENT_SECRET,
        webhook_secret=settings.GITHUB_APP_WEBHOOK_SECRET,
    )
    github_integration.register(registry)

    repository_provider = registry.get_repository_provider("github")
    output_provider = registry.get_output_provider("github")
    pipeline = Pipeline(
        repository_provider=repository_provider,
        output_provider=output_provider,
    )

    # Pre-fetch base snapshot for repository metadata metrics
    print("Fetching base repository snapshot for metrics...")
    file_count = 0
    source_bytes = 0
    try:
        snapshot = await repository_provider.fetch_repository_at_sha(repo_ref, base_sha)
        file_count = len(snapshot.files)
        source_bytes = sum(len(content) for content in snapshot.files.values())
    except Exception as e:  # noqa: BLE001 -- benchmarking must survive individual PR failures
        print(f"Failed to fetch base snapshot: {e}")

    wall_clock_start = time.perf_counter()
    context = None

    try:
        # Run pipeline
        context = await pipeline.run(analysis_request_obj)

        if context.error:
            print(f"Pipeline error: {context.error}")
            raise context.error

        # Render context / serialize before LLM
        pipeline.render_review_context(context)
        pipeline.serialize_llm_context(context)

        # Checkpoint: before LLM request
        profiler.log_memory("before LLM request")

        # Call LLM
        pipeline.generate_llm_comment(
            context,
            repository=repo_name,
            pr_number=str(pr_number),
            language=context.language or "unknown",
        )

        # Checkpoint: after LLM request
        profiler.log_memory("after LLM request")

    finally:
        wall_clock_duration = time.perf_counter() - wall_clock_start

        # Get metrics
        symbol_count = 0
        call_edge_count = 0
        ref_edge_count = 0

        if context:
            if context.repository_view:
                try:
                    symbol_count, call_edge_count, ref_edge_count = get_view_metrics(context.repository_view)
                except Exception as e:  # noqa: BLE001 -- benchmarking must survive individual PR failures
                    print(f"Failed to extract metrics from RepositoryView: {e}")
            elif context.head_repository_model:
                if context.head_repository_model.symbols:
                    symbol_count = len(context.head_repository_model.symbols)
                if (
                    context.head_repository_model.call_graph
                    and context.head_repository_model.call_graph.edges
                ):
                    call_edge_count = len(
                        context.head_repository_model.call_graph.edges
                    )
                if (
                    context.head_repository_model.reference_graph
                    and context.head_repository_model.reference_graph.edges
                ):
                    ref_edge_count = len(
                        context.head_repository_model.reference_graph.edges
                    )

        # Stop profiler and get checkpoints
        profiler_checkpoints = dict(profiler.checkpoints)
        peak_rss_overall = profiler.peak_rss
        profiler.stop()

    return {
        "pr_url": pr_url,
        "repo_name": repo_name,
        "pr_number": pr_number,
        "wall_clock_duration": wall_clock_duration,
        "file_count": file_count,
        "source_bytes": source_bytes,
        "symbol_count": symbol_count,
        "call_edge_count": call_edge_count,
        "ref_edge_count": ref_edge_count,
        "checkpoints": profiler_checkpoints,
        "peak_rss_overall": peak_rss_overall,
    }


async def run_all():
    prs = [
        "https://github.com/pallets/click/pull/3762",
        "https://github.com/polarsource/polar/pull/9204",
        "https://github.com/PostHog/posthog/pull/72474",
    ]

    results = {}
    for pr in prs:
        try:
            res = await run_pr_analysis_direct(pr)
            if res:
                results[pr] = res
        except Exception as e:  # noqa: BLE001 -- benchmarking must survive individual PR failures
            print(f"Failed to benchmark {pr}: {e}")
            import traceback

            traceback.print_exc()

    # Save results
    os.makedirs("logs", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    json_path = f"logs/memory_benchmark_results_{timestamp}.json"
    with open(json_path, "w") as f:  # noqa: ASYNC230 -- one-shot benchmark script
        json.dump(results, f, indent=2)
    # Also write to base file for latest results convenience
    with open("logs/memory_benchmark_results.json", "w") as f:  # noqa: ASYNC230 -- one-shot script
        json.dump(results, f, indent=2)

    print(
        f"\nBenchmark completed. Results saved to {json_path} and logs/memory_benchmark_results.json"
    )

    # Generate the Markdown baseline file
    generate_markdown_report(results)


def generate_markdown_report(results):
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    report_path = f"docs/memory-optimization-baseline-{timestamp}.md"
    os.makedirs("docs", exist_ok=True)

    lines = []
    lines.append("# Memory Optimization Baseline")
    lines.append("")
    lines.append(
        "> **Scope** – Baseline memory and execution metrics across small, medium, and large repositories."
    )
    lines.append("")

    # Summary table
    lines.append("## Repository Metrics Summary")
    lines.append("")
    lines.append(
        "| Repository | File Count | Source Bytes | Symbol Count | Call Edges | Reference Edges | Duration (s) | Peak RSS (MB) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")

    for res in results.values():
        lines.append(
            f"| {res['repo_name']} | {res['file_count']} | {res['source_bytes']} | {res['symbol_count']} | "
            f"{res['call_edge_count']} | {res['ref_edge_count']} | {res['wall_clock_duration']:.2f} | {res['peak_rss_overall']:.1f} |"
        )
    lines.append("")

    # Checkpoint detailed tables
    lines.append("## Checkpoint Details (RSS / Peak RSS in MB)")
    lines.append("")

    for res in results.values():
        lines.append(f"### {res['repo_name']} (PR #{res['pr_number']})")
        lines.append("")
        lines.append("| Checkpoint | Current RSS (MB) | Peak RSS (MB) |")
        lines.append("|---|---|---|")

        # Sort/order checkpoints logically
        ordered_stages = [
            "request start",
            "After repository facts & overlay load",
            "After Change Compiler",
            "After Behavior Compiler",
            "After Operational Compiler",
            "After Engineering Discovery Compiler",
            "After Discovery IR Compiler",
            "After system-model construction",
            "After ReviewContext Compiler",
            "After LLMContext Compiler",
            "After context generation",
            "before LLM request",
            "after LLM request",
            "After base repository download",
            "After parsing",
            "After symbol extraction",
            "After endpoint extraction",
            "After dependency/relationship extraction",
            "After base graph compilation",
            "After base graph load",
            "After base RepositoryModel",
            "After head source load",
            "Before graph clone",
            "peak during graph clone",
            "After graph clone",
            "After GraphPatcher",
            "After head RepositoryModel",
        ]

        for stage in ordered_stages:
            if stage in res["checkpoints"]:
                pt = res["checkpoints"][stage]
                lines.append(
                    f"| {stage} | {pt['current_rss']:.1f} | {pt['peak_rss']:.1f} |"
                )
        lines.append("")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Report written to {report_path}")

    # Also write to base file for latest results convenience
    base_report_path = "docs/memory-optimization-baseline.md"
    with open(base_report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Latest report updated at {base_report_path}")


if __name__ == "__main__":
    asyncio.run(run_all())
