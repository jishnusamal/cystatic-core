"""
Orchestrator — coordinates the new evidence-driven pipeline.

Architecture:
  PR → LanguageAdapter.analyze(diff) → SemanticGraph → ReviewPipeline → EvidencePacket → Result

The orchestrator bridges the API layer with the new core engine pipeline.
Subclasses only differ in how they prepare analysis inputs (FULL_FILE vs DIFF_ONLY).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Optional

from language_adapters.ir.semantic_graph import SemanticGraph
from language_adapters.interfaces.adapter import LanguageAdapter
from schemas import AnalyzeRequest
from api.models import persist_analysis_result
from core_engine.pipelines.review_pipeline import ReviewPipeline
from core_engine.models.packet import EvidencePacket
from source_adapters.github.bot import (
    GitHubBot,
    GitHubSource,
    GitHubPublisher,
)


class AnalysisMode(Enum):
    """Mode of analysis — determines how inputs are prepared."""
    FULL_FILE = auto()
    DIFF_ONLY = auto()


def _get_analysis_mode_str(mode: AnalysisMode) -> str:
    return mode.name


class BaseOrchestrator:
    """Base orchestrator with common pipeline execution flow.

    Subclasses only need to implement _prepare_inputs().
    Everything else is shared.
    """

    def __init__(
        self,
        request: AnalyzeRequest | dict[str, Any],
        source: GitHubBot,
        language: LanguageAdapter,
        publisher: GitHubPublisher | None = None,
        failure_simulation_llm: Any | None = None,
    ):
        self.request = request
        self.source = source
        self.language = language
        self.publisher = publisher
        self.failure_simulation_llm = failure_simulation_llm
        self._pipeline = ReviewPipeline()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_pr_analysis(self) -> dict[str, Any]:
        """Execute the full analysis pipeline.

        Template method — subclasses only override _prepare_inputs().

        Pipeline:
          1. Prepare inputs (fetch diff, file contents)
          2. Run language adapter to build SemanticGraph
          3. Run ReviewPipeline to build EvidencePacket
          4. Format result dict for downstream consumers
        """
        print("─" * 60)
        print("STAGE 1: Input Preparation")
        print("─" * 60)
        prepared = self._prepare_inputs()

        print("─" * 60)
        print("STAGE 2: Language Adapter Analysis → SemanticGraph")
        print("─" * 60)
        raw_graph: SemanticGraph = self.language.analyze(
            diff=prepared["diff_ir"],
            file_contents=prepared.get("file_contents"),
        )

        print("─" * 60)
        print("STAGE 3: ReviewPipeline → EvidencePacket")
        print("─" * 60)
        try:
            packet: EvidencePacket = self._pipeline.run(raw_graph)
        except ValueError as exc:
            print(f"Pipeline validation warning: {exc}")
            packet, warnings = self._pipeline.run_with_warnings(raw_graph)
            if warnings:
                print(f"  Warnings: {len(warnings)}")

        print("─" * 60)
        print("PIPELINE COMPLETE — Packet Summary")
        print("─" * 60)
        print(f"  signals:             {len(packet.signals)}")
        print(f"  execution_paths:     {len(packet.execution_paths)}")
        print(f"  combined_evidence:   {len(packet.combined_evidence)}")
        print(f"  confidence:          {packet.confidence_summary}")
        print(f"  estimated_tokens:    {packet.estimated_tokens}")
        print("─" * 60)

        return self._build_result(
            repo=self._get_repo(),
            pr_number=self._get_pr_number(),
            analysis_mode=self._get_analysis_mode(),
            packet=packet,
        )

    def publish_comments(self, result: dict[str, Any]) -> None:
        """Render and publish PR comment."""
        comment = self._render_pr_comment("github/pr_comment.md.j2", result)
        result["generated_comment"] = comment
        repo = self._get_repo()
        pr_number = self._get_pr_number()
        print(f"Publishing comment to {repo} PR #{pr_number}:\n{comment}")

        if self.publisher is not None:
            self.publisher.post_comment(repo, pr_number, comment)

    async def log_run(self, result: dict[str, Any]) -> None:
        """Persist analysis run to database."""
        await persist_analysis_result(result)
        repo = self._get_repo()
        pr_number = self._get_pr_number()
        print(f"Logged analysis run for {repo} PR #{pr_number}")

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    def _prepare_inputs(self) -> dict[str, Any]:
        """Prepare inputs for analysis. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _prepare_inputs")

    def _get_repo(self) -> str:
        if isinstance(self.request, AnalyzeRequest):
            return self.request.repo
        return self.request.get("repo", "example/repo")  # type: ignore[union-attr]

    def _get_pr_number(self) -> int:
        if isinstance(self.request, AnalyzeRequest):
            return self.request.pr_number
        return self.request.get("pr_number", 1)  # type: ignore[union-attr]

    def _get_analysis_mode(self) -> AnalysisMode:
        raise NotImplementedError("Subclasses must implement _get_analysis_mode")

    # ------------------------------------------------------------------
    # Result formatting
    # ------------------------------------------------------------------

    def _build_result(
        self,
        repo: str,
        pr_number: int,
        analysis_mode: AnalysisMode,
        packet: EvidencePacket,
    ) -> dict[str, Any]:
        """Convert EvidencePacket into the result dict format expected by callers.

        The result dict is backward-compatible with:
          - api/user/urls.py (API response)
          - workers/analyze_pr.py (worker result)
          - api/models.py persist_analysis_result()
          - templates/github/pr_comment.md.j2 (Jinja template)
        """
        packet_dict = packet.to_dict()

        # Derive a simple verdict from the evidence
        verdict = self._derive_verdict(packet)

        # Build failure simulation output compatible with the Jinja template
        failure_simulation = self._build_failure_simulation(packet, verdict)

        return {
            "repo": repo,
            "pr_number": pr_number,
            "analysis_mode": _get_analysis_mode_str(analysis_mode),
            "verdict": verdict,
            "pr_risk_level": self._derive_risk_level(packet),
            "pr_risk_score": self._derive_risk_score(packet),
            "failure_simulation": failure_simulation,
            "evidence_packet": packet_dict,
            "signals": [s.to_dict() for s in packet.signals],
            "execution_paths": [p.to_dict() for p in packet.execution_paths],
            "confidence_summary": packet.confidence_summary,
            "summary": packet.summary,
            "compressed_for_llm": packet_dict,
            "entry_points_affected": self._extract_entrypoints(packet),
            "system_impact": self._extract_system_impact(packet),
            "excluded_files": [],
            "changed_symbols": [],
            "risk_patterns": [],
            "risk_anchors": [],
            "impact_evidence": [],
            "side_effects": [],
            "constraints": [],
            "business_objects": [],
            "change_influence": [],
            "risk_zones": [],
            "domains": [],
            "confidence": self._avg_confidence(packet.confidence_summary),
            "evidence_clusters": [],
            "scenarios": [],
            "hypotheses": [],
            "llm_input_packet": packet_dict,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _derive_verdict(self, packet: EvidencePacket) -> str:
        """Derive a verdict from the evidence packet.

        Heuristic:
          - High-confidence combined evidence about critical areas → BLOCK
          - Any combined evidence → REVIEW_REQUIRED
          - Otherwise → APPROVE (or REVIEW_REQUIRED if signals exist)
        """
        if not packet.signals:
            return "APPROVE"

        # Check for high-risk combined evidence
        for ce in packet.combined_evidence:
            if ce.confidence >= 0.8:
                return "BLOCK"
            if ce.confidence >= 0.6:
                return "REVIEW_REQUIRED"

        # Check for signals about critical areas
        critical_signal_names = {
            "PersistenceWriteAdded",
            "ValidationModified",
            "ValidationRemoved",
            "TransactionBoundaryChanged",
            "NewExternalCall",
            "AuthRemoved",
        }
        for s in packet.signals:
            if s.name in critical_signal_names:
                return "REVIEW_REQUIRED"

        # Check coverage gaps
        if packet.coverage_evidence:
            untested_count = 0
            if packet.coverage_evidence.untested_entrypoints:
                untested_count += len(packet.coverage_evidence.untested_entrypoints)
            if untested_count > 0:
                return "REVIEW_REQUIRED"

        return "APPROVE"

    def _derive_risk_level(self, packet: EvidencePacket) -> str:
        """Derive a risk level string from the packet."""
        verdict = self._derive_verdict(packet)
        if verdict == "BLOCK":
            return "HIGH"
        if verdict == "REVIEW_REQUIRED":
            if packet.combined_evidence:
                return "MEDIUM"
            return "LOW"
        return "LOW"

    def _derive_risk_score(self, packet: EvidencePacket) -> float:
        """Derive a numeric risk score from the packet."""
        if not packet.signals:
            return 0.0

        base = 0.0
        for ce in packet.combined_evidence:
            base += ce.confidence * 0.2
        for s in packet.signals:
            base += 0.05

        return min(round(base, 2), 1.0)

    def _build_failure_simulation(
        self, packet: EvidencePacket, verdict: str
    ) -> dict[str, Any]:
        """Build failure simulation output from evidence packet.

        This produces output compatible with pr_comment.md.j2 template.
        """
        primary_concern = None
        additional_observations = []

        # Build primary concern from highest-confidence combined evidence
        if packet.combined_evidence:
            best = max(packet.combined_evidence, key=lambda c: c.confidence)
            primary_concern = {
                "title": best.description[:100],
                "why_blocking": (
                    f"Combined evidence from {len(best.source_signals)} sources "
                    f"indicates {best.description}"
                ),
                "execution_path": (
                    f"Path involves {len(best.node_ids)} code locations"
                ),
                "customer_or_business_impact": (
                    "Changes to this code path may affect production stability"
                    if best.confidence >= 0.7
                    else "Potential impact on system behavior"
                ),
                "why_existing_tests_miss_it": (
                    f"Detected by {len(best.source_signals)} independent "
                    f"analysis signals"
                ),
                "confidence_rationale": (
                    f"Confidence: {best.confidence:.2f} based on "
                    f"deterministic analysis"
                ),
                "required_validation": (
                    "Add tests covering the affected code path"
                ),
            }

            # Remaining combined evidence → additional observations
            for ce in packet.combined_evidence[1:]:
                additional_observations.append({
                    "title": ce.description[:100],
                    "observation": (
                        f"Confidence {ce.confidence:.2f} — "
                        f"{len(ce.source_signals)} signals involved"
                    ),
                    "symbols": ce.node_ids[:5],
                })

        # Add execution path info as observations
        if packet.execution_paths:
            unique_paths = len(set(p.entrypoint for p in packet.execution_paths))
            additional_observations.append({
                "title": f"Execution Paths ({unique_paths} unique)",
                "observation": (
                    f"Analysis found {unique_paths} unique execution paths "
                    f"through the changed code. Total paths: {len(packet.execution_paths)}."
                ),
                "symbols": [p.entrypoint for p in packet.execution_paths[:5]],
            })

        # Add coverage info
        if packet.coverage_evidence:
            untested = (
                len(packet.coverage_evidence.untested_entrypoints)
                + len(packet.coverage_evidence.untested_persistence_paths)
                + len(packet.coverage_evidence.untested_validation)
            )
            if untested > 0:
                additional_observations.append({
                    "title": f"Untested Code ({untested} paths)",
                    "observation": (
                        f"Found {untested} untested code paths including "
                        f"{len(packet.coverage_evidence.untested_entrypoints)} "
                        f"entrypoints."
                    ),
                    "symbols": packet.coverage_evidence.untested_entrypoints[:5],
                })

        required_tests = []
        if packet.coverage_evidence and packet.coverage_evidence.untested_entrypoints:
            required_tests = [
                f"Test entrypoint: {ep}"
                for ep in packet.coverage_evidence.untested_entrypoints[:3]
            ]

        return {
            "verdict": verdict,
            "executive_summary": packet.summary or f"Analysis complete: {verdict}",
            "primary_concern": primary_concern,
            "additional_observations": additional_observations,
            "required_tests": required_tests,
            "reviewer_questions": [],
            "merge_recommendation": (
                "Safe to merge"
                if verdict == "APPROVE"
                else "Requires review"
                if verdict == "REVIEW_REQUIRED"
                else "Blocked by concerns"
            ),
        }

    def _extract_entrypoints(self, packet: EvidencePacket) -> list[dict[str, Any]]:
        """Extract entry points from execution paths."""
        seen: set[str] = set()
        entrypoints = []
        for path in packet.execution_paths:
            if path.entrypoint not in seen:
                seen.add(path.entrypoint)
                entrypoints.append({
                    "name": path.entrypoint,
                    "path_count": sum(
                        1 for p in packet.execution_paths
                        if p.entrypoint == path.entrypoint
                    ),
                })
        return entrypoints

    def _extract_system_impact(self, packet: EvidencePacket) -> list[dict[str, Any]]:
        """Extract system impact from execution paths."""
        services: dict[str, int] = {}
        for path in packet.execution_paths:
            for service in path.affected_services:
                services[service] = services.get(service, 0) + 1
        return [
            {"area": service, "impact_count": count}
            for service, count in sorted(
                services.items(), key=lambda x: -x[1]
            )
        ]

    @staticmethod
    def _avg_confidence(confidence_summary: dict[str, float]) -> float:
        if not confidence_summary:
            return 1.0
        return round(
            sum(confidence_summary.values()) / len(confidence_summary), 2
        )

    def _render_pr_comment(self, template_name: str, result: dict) -> str:
        """Render PR comment from template."""
        from jinja2 import Environment, FileSystemLoader, Template
        from pathlib import Path

        base_dir = Path(__file__).resolve().parent.parent
        env = Environment(loader=FileSystemLoader(base_dir / "templates"))
        jinja_template: Template = env.get_template(template_name)
        failure_simulation = result.get("failure_simulation", {})
        if not isinstance(failure_simulation, dict):
            failure_simulation = {}
        return jinja_template.render(
            verdict=result.get("verdict", "UNKNOWN"),
            failure_simulation=failure_simulation,
        )


class Orchestrator(BaseOrchestrator):
    """Repo-aware orchestrator using GitHub PR diff + full file snapshots."""

    def __init__(
        self,
        request: AnalyzeRequest,
        source: GitHubSource,
        language: LanguageAdapter,
        publisher: GitHubPublisher | None = None,
        failure_simulation_llm: Any | None = None,
    ):
        super().__init__(request, source, language, publisher, failure_simulation_llm)

    def _prepare_inputs(self) -> dict[str, Any]:
        """Prepare inputs in FULL_FILE mode."""
        assert isinstance(self.request, AnalyzeRequest), (
            "Orchestrator requires AnalyzeRequest"
        )
        repo = self.request.repo
        pr_number = self.request.pr_number

        # Fetch diff from GitHub
        diff_ir = self.source.fetch_diff(repo, pr_number)

        # Fetch file contents for full AST analysis
        file_contents: dict[str, str] = {}
        for file_diff in diff_ir.files:
            try:
                snapshot = self.source.fetch_file_at_sha(
                    repo, file_diff.file_path, self.source.get_head_sha(repo, pr_number)
                )
                file_contents[file_diff.file_path] = snapshot.content
            except Exception:
                continue

        return {
            "diff_ir": diff_ir,
            "file_contents": file_contents,
            "mode": "FULL_FILE",
        }

    def _get_analysis_mode(self) -> AnalysisMode:
        return AnalysisMode.FULL_FILE


class DiffOrchestrator(BaseOrchestrator):
    """Demo-safe orchestrator using raw diff text (no repo access)."""

    def __init__(
        self,
        request: dict[str, Any],
        source: GitHubSource,
        language: LanguageAdapter,
        publisher: GitHubPublisher | None = None,
        failure_simulation_llm: Any | None = None,
    ):
        super().__init__(request, source, language, publisher, failure_simulation_llm)

    def _prepare_inputs(self) -> dict[str, Any]:
        """Prepare inputs in DIFF_ONLY mode.

        The diff text is passed directly in the request dict.
        The source adapter is used to parse the raw diff text.
        """
        diff_text = self.request.get("diff", "")

        # Use the source adapter's _format_diff to parse the raw diff text
        # We call through to the bot's diff parser
        diff_ir = self.source.fetch_diff(
            # Use a dummy repo since we already have the diff text
            self.request.get("repo", "example/repo"),
            self.request.get("pr_number", 1),
        )

        # Override with the provided diff if available
        if diff_text:
            # Parse the raw diff text using the bot's formatter
            from source_adapters.github.bot import GitHubBot

            temp_bot = GitHubBot()
            diff_ir = temp_bot._format_diff(diff_text)

        return {
            "diff_ir": diff_ir,
            "file_contents": {},
            "mode": "DIFF_ONLY",
        }

    def _get_analysis_mode(self) -> AnalysisMode:
        return AnalysisMode.DIFF_ONLY