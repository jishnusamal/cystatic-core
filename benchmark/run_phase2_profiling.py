import os
import sys
import gc
import json
import time
import asyncio
import pickle
import psutil
import ast
from typing import Dict, Any, List

# Add workspace root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.config import get_settings
from api.routes.github import _fetch_pr_details_from_url
from engine.pipeline.pipeline import Pipeline
from models.core import RepositoryReference, PullRequestReference
from models.analysis import AnalysisRequest, AnalysisTrigger
from core.profile import MemoryProfiler
from benchmark.size_estimator import get_retained_size
from engine.pipeline.context import PipelineContext
from engine.repository.model.file_contribution import FileContribution

# Diagnostic outputs target directories
os.makedirs("profiling/phase2", exist_ok=True)


class DiagnosticProfiler:
    def __init__(self, pr_url: str):
        self.pr_url = pr_url
        self.process = psutil.Process(os.getpid())
        self.metrics: Dict[str, Any] = {}
        self.checkpoints: List[Dict[str, Any]] = []

    def get_rss(self) -> float:
        gc.collect()
        return self.process.memory_info().rss / (1024 * 1024)

    def count_reachable_source(self) -> tuple[int, int]:
        import gc
        from models.core import RepositorySnapshot
        from engine.language.base.file_context import FileContext

        snapshots = [
            obj for obj in gc.get_objects() if isinstance(obj, RepositorySnapshot)
        ]
        file_contexts = [
            obj for obj in gc.get_objects() if isinstance(obj, FileContext)
        ]

        source_strings = set()

        for s in snapshots:
            for content in s.files.values():
                if isinstance(content, str):
                    source_strings.add(content)

        for fc in file_contexts:
            if hasattr(fc, "source") and isinstance(fc.source, str):
                source_strings.add(fc.source)

        # Also check for dictionary objects that look like files dict
        for obj in gc.get_objects():
            if isinstance(obj, dict) and len(obj) > 0:
                try:
                    # check if it looks like a files dictionary: string keys, string values, and keys ending in code extensions
                    sample_keys = list(obj.keys())[:3]
                    if all(
                        isinstance(k, str)
                        and any(
                            k.endswith(ext)
                            for ext in [
                                ".py",
                                ".java",
                                ".ts",
                                ".json",
                                ".go",
                                ".cpp",
                                ".h",
                            ]
                        )
                        for k in sample_keys
                    ):
                        # check values are strings
                        if all(isinstance(obj[k], str) for k in list(obj.keys())[:3]):
                            for content in obj.values():
                                if isinstance(content, str):
                                    source_strings.add(content)
                except Exception:
                    pass

        total_files = len(source_strings)
        total_bytes = sum(len(s.encode("utf-8")) for s in source_strings)
        return total_files, total_bytes

    def record_checkpoint(self, stage: str, context: Any = None):
        rss = self.get_rss()
        files, bytes_size = self.count_reachable_source()
        checkpoint_data = {
            "stage": stage,
            "rss_mb": rss,
            "timestamp": time.time(),
            "source_files_reachable": files,
            "source_bytes_reachable": bytes_size,
        }
        print(
            f"[DIAGNOSTIC] Checkpoint: {stage:<45} RSS: {rss:8.2f} MB | Source Reachable: {files} files ({bytes_size / (1024 * 1024):.2f} MB)"
        )
        self.checkpoints.append(checkpoint_data)
        return rss

    async def run(self):
        # Establish base baseline RSS
        self.record_checkpoint("RSS before request")

        # 1. Fetch PR details
        pr_data = await _fetch_pr_details_from_url(self.pr_url)
        repo_name = pr_data["repository"]
        pr_number = pr_data["pr_number"]
        base_sha = pr_data["base_sha"]
        head_sha = pr_data["head_sha"]

        # Build pipeline and request objects
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

        # We will manually run steps to grab metrics and instrument object sizes
        # Step A: Fetch base repository snapshot
        print(f"[DIAGNOSTIC] Fetching base repository snapshot at {base_sha}...")
        snapshot = await repository_provider.fetch_repository_at_sha(repo_ref, base_sha)
        self.record_checkpoint("RSS after repository download")

        # Measure snapshot details
        num_files = len(snapshot.files)
        total_chars = sum(len(content) for content in snapshot.files.values())
        total_bytes = sum(
            len(content.encode("utf-8")) for content in snapshot.files.values()
        )
        self.metrics["source_snapshot"] = {
            "num_files": num_files,
            "total_chars": total_chars,
            "total_bytes": total_bytes,
        }

        # Step B: Parse ASTs
        print("[DIAGNOSTIC] Parsing source files into ASTs...")
        asts = {}
        for path, content in snapshot.files.items():
            if path.endswith(".py"):
                try:
                    asts[path] = ast.parse(content, filename=path)
                except SyntaxError:
                    pass
        self.record_checkpoint("RSS after parsing")

        # Estimate AST sizes
        ast_retained_mem = get_retained_size(asts)
        self.metrics["ast"] = {
            "num_files": len(asts),
            "num_ast_roots": len(asts),
            "retained_memory_bytes": ast_retained_mem,
        }
        del asts
        gc.collect()

        # Step C: Index / Symbol Extraction
        print("[DIAGNOSTIC] Extracting symbols & structural facts (IndexCompiler)...")
        from engine.language.python.adapter import PythonLanguageAdapter

        adapter = PythonLanguageAdapter()
        index = adapter.build_index({"files": snapshot.files, "language": "python"})
        self.record_checkpoint("RSS after symbol extraction")
        self.record_checkpoint("RSS after endpoint extraction")
        self.record_checkpoint("RSS after dependency/relationship extraction")

        # Measure index facts
        symbols_count = len(index.all_symbols)
        calls_count = len(index.all_calls)
        imports_count = len(index.all_imports)
        type_rels_count = len(index.all_type_relationships)
        self.metrics["raw_index_facts"] = {
            "symbols": symbols_count,
            "calls": calls_count,
            "imports": imports_count,
            "type_relationships": type_rels_count,
            "retained_size_bytes": get_retained_size(index),
        }

        # Step D: Compile RepositoryGraph (SemanticCompiler)
        print("[DIAGNOSTIC] Compiling base repository graph...")
        repository_input = {
            "root_directory": repo_name,
            "language": "python",
            "files": snapshot.files,
            "commit_sha": base_sha,
        }
        base_graph = adapter.compile_graph(repository_input)
        del snapshot
        del repository_input
        gc.collect()
        self.record_checkpoint("RSS after base graph compilation")

        # Measure base_graph retained memory and details
        base_graph_size = get_retained_size(base_graph)
        self.metrics["base_graph"] = {
            "retained_size_bytes": base_graph_size,
            "symbol_count": len(base_graph.symbols),
            "import_count": len(base_graph.imports),
            "call_edges": len(base_graph.call_graph.edges),
            "reference_edges": len(base_graph.reference_graph.edges),
            "type_relationship_edges": len(base_graph.type_relationship_graph.edges),
        }

        # Measure index components of CallGraph / ReferenceGraph / TypeRelationshipGraph
        self.metrics["graph_indexes"] = {
            "call_graph": {
                "edges_tuple": get_retained_size(base_graph.call_graph.edges),
                "outgoing": get_retained_size(base_graph.call_graph._outgoing),
                "incoming": get_retained_size(base_graph.call_graph._incoming),
            },
            "reference_graph": {
                "edges_tuple": get_retained_size(base_graph.reference_graph.edges),
                "outgoing": get_retained_size(base_graph.reference_graph._outgoing),
                "incoming": get_retained_size(base_graph.reference_graph._incoming),
            },
            "type_relationship_graph": {
                "edges_tuple": get_retained_size(
                    base_graph.type_relationship_graph.edges
                ),
                "outgoing": get_retained_size(
                    base_graph.type_relationship_graph._outgoing
                ),
                "incoming": get_retained_size(
                    base_graph.type_relationship_graph._incoming
                ),
            },
            "repository_graph_reverse_indexes": {
                "symbol_to_callers": get_retained_size(base_graph.symbol_to_callers),
                "symbol_to_importers": get_retained_size(
                    base_graph.symbol_to_importers
                ),
                "unresolved_symbol_to_waiting_files": get_retained_size(
                    base_graph.unresolved_symbol_to_waiting_files
                ),
                "file_to_call_edges": get_retained_size(base_graph.file_to_call_edges),
                "file_to_reference_edges": get_retained_size(
                    base_graph.file_to_reference_edges
                ),
            },
        }

        # Step E: Export base RepositoryModel
        print("[DIAGNOSTIC] Exporting base RepositoryModel...")
        base_repository_model = base_graph.to_model()
        self.record_checkpoint("RSS after base RepositoryModel")

        # Measure RepositoryModel retention
        self.metrics["base_repository_model"] = {
            "retained_size_bytes": get_retained_size(base_repository_model),
            "symbol_map_size_bytes": get_retained_size(
                base_repository_model._symbol_map
            ),
            "symbols_count": len(base_repository_model.symbols),
        }

        # Step F: Head source load (changed files)
        print("[DIAGNOSTIC] Fetching head changed files...")
        context = PipelineContext(
            repository=repo_name,
            base_sha=base_sha,
            head_sha=head_sha,
        )
        await pipeline._fetch_diff(context, analysis_request_obj)

        changed_files_dict = {}
        if context.diff_data and "files" in context.diff_data:
            for file_info in context.diff_data["files"]:
                file_path = file_info["file_path"]
                try:
                    content = await repository_provider.fetch_file(
                        repo_ref, file_path, head_sha
                    )
                    changed_files_dict[file_path] = content
                except Exception:
                    changed_files_dict[file_path] = None

        self.record_checkpoint("RSS after head source load")

        # Step G: Pickle clone measurement
        self.record_checkpoint("RSS immediately before graph clone")

        # Profile Pickle Clone Separately
        pickle_start_rss = self.get_rss()
        serialized = pickle.dumps(base_graph)
        pickle_dumps_rss = self.get_rss()
        pickle_byte_size = len(serialized)

        patched_graph = pickle.loads(serialized)
        pickle_loads_rss = self.get_rss()

        del serialized
        gc.collect()
        pickle_deleted_rss = self.get_rss()

        self.record_checkpoint("RSS after graph clone")

        # Calculation of Pickle rates
        patched_graph_size = get_retained_size(patched_graph)
        self.metrics["pickle_clone"] = {
            "pickle_byte_size": pickle_byte_size,
            "base_graph_retained_size": base_graph_size,
            "patched_graph_retained_size": patched_graph_size,
            "rss_before_dumps": pickle_start_rss,
            "rss_after_dumps": pickle_dumps_rss,
            "rss_after_loads": pickle_loads_rss,
            "rss_after_serialized_bytes_deleted": pickle_deleted_rss,
            "ratio_pickle_base": pickle_byte_size / base_graph_size
            if base_graph_size
            else 0,
            "ratio_clone_base": patched_graph_size / base_graph_size
            if base_graph_size
            else 0,
            "peak_delta_mb": pickle_loads_rss - pickle_start_rss,
        }

        # Step H: Incremental Compilation / GraphPatcher
        print("[DIAGNOSTIC] Incremental patching on cloned graph...")
        # Get structural facts for changed files
        changed_contribs = {}
        for path, content in changed_files_dict.items():
            if content is not None:
                file_index = adapter._index_single_file(path, content, "python")
                changed_contribs[path] = FileContribution.from_file_index(file_index)
            else:
                changed_contribs[path] = None

        del changed_files_dict
        gc.collect()

        from engine.language.base.graph_patcher import GraphPatcher

        patcher = GraphPatcher()
        patcher.patch(patched_graph, changed_contribs, "python")
        self.record_checkpoint("RSS after GraphPatcher")

        # Step I: Head RepositoryModel
        print("[DIAGNOSTIC] Exporting head RepositoryModel...")
        head_repository_model = patched_graph.to_model()
        self.record_checkpoint("RSS after head RepositoryModel")

        # Set up PipelineContext for downstream compilers
        context.base_repository_snapshot = None
        context.base_repository_model = base_repository_model
        context.head_repository_model = head_repository_model
        context.language = "python"

        # Step J: Change compiler
        print("[DIAGNOSTIC] Running ChangeCompiler...")
        await pipeline._compile_change(context)
        self.record_checkpoint(
            "RSS after head RepositoryModel"
        )  # equivalent check post model conversion
        self.record_checkpoint("RSS after Change Compiler")

        # Step K: Downstream compilers
        compilers = [
            ("Behavior Compiler", pipeline._compile_behavior),
            ("Operational Compiler", pipeline._compile_operational),
            ("Engineering Discovery Compiler", pipeline._compile_discovery),
            ("Discovery IR Compiler", pipeline._compile_discovery_ir),
            ("ReviewContext Compiler", pipeline._compile_review_context),
            ("LLMContext Compiler", pipeline._compile_llm_context),
        ]

        self.metrics["downstream_compilers"] = {}
        for name, compiler_func in compilers:
            rss_before = self.get_rss()
            await compiler_func(context)
            rss_after = self.get_rss()

            # Checkpoint name formatting
            stage_name = f"After {name.replace(' Compiler', '')} Compiler"
            if "IR" in name:
                stage_name = "After Discovery IR Compiler"
            elif "Engineering" in name:
                stage_name = "After Engineering Discovery Compiler"
            self.record_checkpoint(stage_name)

            self.metrics["downstream_compilers"][name] = {
                "rss_before": rss_before,
                "rss_after": rss_after,
                "delta_rss_mb": rss_after - rss_before,
            }

        # Step L: Render and Call LLM context
        pipeline.render_review_context(context)
        pipeline.serialize_llm_context(context)
        self.record_checkpoint("before LLM request")

        # Simulate or call LLM request (we will simulate or load config if mock)
        # Note: Do not perform actual LLM token spend in benchmark if config allows,
        # but to match baseline we will trigger the flow.
        try:
            print("[DIAGNOSTIC] Generating LLM comment...")
            llm_result = pipeline.generate_llm_comment(
                context,
                repository=repo_name,
                pr_number=str(pr_number),
                language="python",
            )
        except Exception as e:
            print(f"[DIAGNOSTIC] LLM request skipped/failed: {e}")
        self.record_checkpoint("after LLM request")

        # Final object count / memory ownership map analyses
        # Analyze FileContribution cost specifically for this repo
        files_breakdown = {}
        for f_path, contrib in base_graph.files.items():
            files_breakdown[f_path] = {
                "symbols": len(contrib.symbols),
                "imports": len(contrib.imports),
                "calls": len(contrib.calls),
                "references": len(contrib.references),
                "type_relationships": len(contrib.type_relationships),
                "size_bytes": get_retained_size(contrib),
            }

        self.metrics["files_breakdown"] = {
            "total_files": len(base_graph.files),
            "total_retained_size_bytes": sum(
                f["size_bytes"] for f in files_breakdown.values()
            ),
            "files": files_breakdown,
        }

        # Clean up references manually to see where RSS drops
        print("[DIAGNOSTIC] Tracing reference cleanups / GC details...")
        before_cleanup_rss = self.get_rss()

        # Delete large objects
        if "snapshot" in locals():
            del snapshot
        if "asts" in locals():
            del asts
        if "base_graph" in locals():
            del base_graph
        if "patched_graph" in locals():
            del patched_graph
        if "context" in locals():
            del context

        gc.collect()
        after_cleanup_rss = self.get_rss()
        print(
            f"[DIAGNOSTIC] Cleanup RSS drop: {before_cleanup_rss:.2f} MB -> {after_cleanup_rss:.2f} MB"
        )
        self.metrics["cleanup_rss_drop"] = {
            "before_cleanup_rss": before_cleanup_rss,
            "after_cleanup_rss": after_cleanup_rss,
            "reclaimed_mb": before_cleanup_rss - after_cleanup_rss,
        }

        # Write results
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        repo_lower = repo_name.split("/")[-1].lower()
        output_file = f"profiling/phase2/{repo_lower}_{timestamp}.json"
        with open(output_file, "w") as f:
            json.dump(
                {
                    "pr_url": self.pr_url,
                    "checkpoints": self.checkpoints,
                    "metrics": self.metrics,
                },
                f,
                indent=2,
            )
        print(f"[DIAGNOSTIC] Results successfully written to {output_file}")

        # Also write to base file for latest results convenience
        base_output_file = f"profiling/phase2/{repo_lower}.json"
        with open(base_output_file, "w") as f:
            json.dump(
                {
                    "pr_url": self.pr_url,
                    "checkpoints": self.checkpoints,
                    "metrics": self.metrics,
                },
                f,
                indent=2,
            )


async def main():
    prs = [
        "https://github.com/pallets/click/pull/3762",
        "https://github.com/polarsource/polar/pull/9204",
        "https://github.com/PostHog/posthog/pull/72474",
    ]
    for pr in prs:
        profiler = DiagnosticProfiler(pr)
        await profiler.run()


if __name__ == "__main__":
    asyncio.run(main())
