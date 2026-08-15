import os
import sys
import json
import time
import asyncio
import psutil
import re

# PYTHONPATH=. infisical run -- uv run python benchmark/run_benchmarks.py

# Add workspace root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.config import get_settings
from api.routes.github import _fetch_pr_details_from_url
from engine.pipeline.pipeline import Pipeline
from models.core import RepositoryReference, PullRequestReference
from models.analysis import AnalysisRequest, AnalysisTrigger
from core.profile import MemoryProfiler, get_current_profiler


async def run_pr_analysis_direct(pr_url: str):
    print(f"\n==================================================")
    print(f"Running direct memory benchmark for: {pr_url}")
    print(f"==================================================")

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

    wall_clock_start = time.perf_counter()
    context = None
    llm_comment = None

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
        llm_result = pipeline.generate_llm_comment(
            context,
            repository=repo_name,
            pr_number=str(pr_number),
            language=context.language or "unknown",
        )

        # Checkpoint: after LLM request
        profiler.log_memory("after LLM request")

        llm_comment = llm_result.get("comment")

    finally:
        wall_clock_duration = time.perf_counter() - wall_clock_start

        # Get metrics
        file_count = 0
        source_bytes = 0
        symbol_count = 0
        call_edge_count = 0
        ref_edge_count = 0

        if context:
            if context.base_repository_snapshot and hasattr(
                context.base_repository_snapshot, "files"
            ):
                file_count = len(context.base_repository_snapshot.files)
                source_bytes = sum(
                    len(content)
                    for content in context.base_repository_snapshot.files.values()
                )

            if context.head_repository_model:
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
        except Exception as e:
            print(f"Failed to benchmark {pr}: {e}")
            import traceback

            traceback.print_exc()

    # Save results
    os.makedirs("logs", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    json_path = f"logs/memory_benchmark_results_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    # Also write to base file for latest results convenience
    with open("logs/memory_benchmark_results.json", "w") as f:
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

    for pr, res in results.items():
        lines.append(
            f"| {res['repo_name']} | {res['file_count']} | {res['source_bytes']} | {res['symbol_count']} | "
            f"{res['call_edge_count']} | {res['ref_edge_count']} | {res['wall_clock_duration']:.2f} | {res['peak_rss_overall']:.1f} |"
        )
    lines.append("")

    # Checkpoint detailed tables
    lines.append("## Checkpoint Details (RSS / Peak RSS in MB)")
    lines.append("")

    for pr, res in results.items():
        lines.append(f"### {res['repo_name']} (PR #{res['pr_number']})")
        lines.append("")
        lines.append("| Checkpoint | Current RSS (MB) | Peak RSS (MB) |")
        lines.append("|---|---|---|")

        # Sort/order checkpoints logically
        ordered_stages = [
            "request start",
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
            "After Change Compiler",
            "After Behavior Compiler",
            "After Operational Compiler",
            "After Engineering Discovery Compiler",
            "After Discovery IR Compiler",
            "After ReviewContext Compiler",
            "After LLMContext Compiler",
            "before LLM request",
            "after LLM request",
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
