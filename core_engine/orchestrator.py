"""
Orchestrator — simplified pipeline coordinator.

Architecture:
  PR → InputPreparation → ChangeUnderstanding → EvidenceBundle → Inference → Review

The orchestrator coordinates pipeline execution. Subclasses only differ
in how they prepare analysis inputs (FULL_FILE vs DIFF_ONLY).
"""
from __future__ import annotations

from typing import Any

from schemas import AnalyzeRequest
from api.models import persist_analysis_result
from language_adapters.python.python_adapter import AnalysisMode
from core_engine.pipelines.input_preparation import InputPreparationPipeline
from core_engine.pipelines.change_understanding import ChangeUnderstandingPipeline
from core_engine.pipelines.evidence import EvidencePipeline
from core_engine.pipelines.inference import InferencePipeline
from core_engine.pipelines.review import ReviewPipeline


class BaseOrchestrator:
    """Base orchestrator with common pipeline execution flow.
    
    Subclasses only need to implement _prepare_analysis_inputs().
    Everything else is shared.
    """
    
    def __init__(self, request, source, language, publisher=None, failure_simulation_llm=None):
        self.request = request
        self.source = source
        self.language = language
        self.publisher = publisher
        self.failure_simulation_llm = failure_simulation_llm

    def run_pr_analysis(self) -> dict[str, Any]:
        """Execute the full analysis pipeline.
        
        Template method - subclasses only override _prepare_analysis_inputs().
        """
        # Stage 1: Input Preparation (mode-specific)
        print("─" * 60)
        print("STAGE 1: Input Preparation")
        print("─" * 60)
        prepared = self._prepare_analysis_inputs()
        
        # Stage 2-5: Common pipeline execution
        print("─" * 60)
        print("STAGE 2: Change Understanding")
        print("─" * 60)
        understanding = ChangeUnderstandingPipeline.run(
            enriched_files=prepared.enriched_files,
            diff_ir=prepared.diff_ir,
            repo_index=prepared.repo_index,
        )

        print("─" * 60)
        print("STAGE 3: Evidence Pipeline")
        print("─" * 60)
        bundle = EvidencePipeline.run(understanding)

        print("─" * 60)
        print("STAGE 4: Inference Pipeline")
        print("─" * 60)
        inference = InferencePipeline.run(bundle)

        print("─" * 60)
        print("STAGE 5: Review Pipeline")
        print("─" * 60)
        review = ReviewPipeline.run(
            bundle=bundle,
            understanding=understanding,
            failure_simulation_llm=self.failure_simulation_llm,
        )

        print("─" * 60)
        print("PIPELINE COMPLETE — Final Object Summary")
        print("─" * 60)
        print(f"  enriched_files:     {len(prepared.enriched_files)}")
        print(f"  excluded_files:     {len(prepared.excluded_files)}")
        print(f"  risk_patterns:      {len(understanding.risk_patterns)}")
        print(f"  changed_symbols:    {len(bundle.changed_symbols)}")
        print(f"  risk_anchors:       {len(bundle.risk_anchors)}")
        print(f"  impact_evidence:    {len(bundle.impact_evidence)}")
        print(f"  side_effects:       {len(bundle.side_effects)}")
        print(f"  constraints:        {len(bundle.constraints)}")
        print(f"  business_objects:   {len(bundle.business_objects)}")
        print(f"  domains:            {len(bundle.domains)}")
        print(f"  confidence:         {bundle.confidence}")
        print(f"  evidence_clusters:  {len(inference.evidence_clusters)}")
        print(f"  hypotheses:         {len(inference.hypotheses)}")
        print(f"  scenarios:          {len(inference.scenarios)}")
        # New output format: primary_concern and additional_observations
        review_output = review.failure_simulation if isinstance(review.failure_simulation, dict) else {}
        has_primary = 1 if review_output.get("primary_concern") else 0
        num_additional = len(review_output.get("additional_observations", []))
        print(f"  primary_concern:             {'yes' if has_primary else 'no'}")
        print(f"  additional_observations:     {num_additional}")
        print(f"  verdict:            {review.verdict}")
        print("─" * 60)

        return self._build_result(
            repo=self._get_repo(),
            pr_number=self._get_pr_number(),
            analysis_mode=self._get_analysis_mode(),
            enriched_files=prepared.enriched_files,
            changed_symbols=[cs.symbol for cs in bundle.changed_symbols],
            risk_anchors=[ra.model_dump() if hasattr(ra, "model_dump") else ra for ra in bundle.risk_anchors],
            impact_evidence=[ev.model_dump() for ev in bundle.impact_evidence],
            side_effects=[se.model_dump() if hasattr(se, "model_dump") else se for se in bundle.side_effects],
            constraints=[c.model_dump() if hasattr(c, "model_dump") else c for c in bundle.constraints],
            business_objects=[bo.model_dump() if hasattr(bo, "model_dump") else bo for bo in bundle.business_objects],
            change_influence=[],
            risk_zones=bundle.domains,
            domains=bundle.domains,
            confidence=bundle.confidence,
            evidence_clusters=inference.evidence_clusters,
            scenarios=inference.scenarios,
            hypotheses=inference.hypotheses,
            failure_simulation=review.failure_simulation,
            verdict=review.verdict,
            excluded_files=prepared.excluded_files,
        )

    def _prepare_analysis_inputs(self) -> Any:
        """Prepare inputs for analysis. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _prepare_analysis_inputs")

    def _get_repo(self) -> str:
        """Get repository identifier."""
        if hasattr(self.request, 'repo'):
            return self.request.repo
        return self.request.get("repo", "example/repo")

    def _get_pr_number(self) -> int:
        """Get PR number."""
        if hasattr(self.request, 'pr_number'):
            return self.request.pr_number
        return self.request.get("pr_number", 1)

    def _get_analysis_mode(self) -> AnalysisMode:
        """Get analysis mode."""
        raise NotImplementedError("Subclasses must implement _get_analysis_mode")

    def _build_result(
        self,
        repo: str,
        pr_number: int,
        analysis_mode: AnalysisMode,
        enriched_files: list[dict],
        changed_symbols: list[str],
        risk_anchors: list[dict],
        impact_evidence: list[dict],
        side_effects: list[dict],
        constraints: list[dict],
        business_objects: list[dict],
        change_influence: list[dict],
        risk_zones: list[str],
        domains: list[str],
        confidence: float,
        evidence_clusters: list[dict],
        scenarios: list[dict],
        hypotheses: list[dict],
        failure_simulation: dict | None = None,
        verdict: str = "UNKNOWN",
        excluded_files: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Build final result from all pipeline outputs."""
        return {
            "repo": repo,
            "pr_number": pr_number,
            "analysis_mode": analysis_mode.value if hasattr(analysis_mode, 'value') else str(analysis_mode),
            "changed_symbols": changed_symbols or [],
            "risk_anchors": risk_anchors or [],
            "impact_evidence": impact_evidence or [],
            "side_effects": side_effects or [],
            "constraints": constraints or [],
            "business_objects": business_objects or [],
            "change_influence": change_influence or [],
            "risk_zones": risk_zones or ["general"],
            "domains": domains or [],
            "confidence": confidence or 1.0,
            "evidence_clusters": evidence_clusters or [],
            "scenarios": scenarios or [],
            "hypotheses": hypotheses or [],
            "failure_simulation": failure_simulation or {},
            "verdict": verdict,
            "excluded_files": excluded_files or [],
        }

    def publish_comments(self, result: dict[str, Any]) -> None:
        """Publish PR comments."""
        comment = self._render_pr_comment("github/pr_comment.md.j2", result)
        result["generated_comment"] = comment
        repo = self._get_repo()
        pr_number = self._get_pr_number()
        print(f"Publishing comment to {repo} PR #{pr_number}:\n{comment}")

    async def log_run(self, result: dict[str, Any]) -> None:
        """Log analysis run."""
        await persist_analysis_result(result)
        repo = self._get_repo()
        pr_number = self._get_pr_number()
        print(f"Logged analysis run for {repo} PR #{pr_number}")

    def _render_pr_comment(self, template_name: str, result: dict) -> str:
        """Render PR comment from template."""
        from jinja2 import Environment, FileSystemLoader, Template
        env = Environment(loader=FileSystemLoader("templates"))
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

    def __init__(self, request: AnalyzeRequest, source, language, publisher=None, failure_simulation_llm=None):
        super().__init__(request, source, language, publisher, failure_simulation_llm)

    def _prepare_analysis_inputs(self):
        """Prepare inputs in FULL_FILE mode."""
        return InputPreparationPipeline.run(
            request=self.request,
            source=self.source,
            language=self.language,
            mode="FULL_FILE",
        )

    def _get_analysis_mode(self) -> AnalysisMode:
        """Get analysis mode for FULL_FILE orchestrator."""
        return AnalysisMode.FULL_FILE


class DiffOrchestrator(BaseOrchestrator):
    """Demo-safe orchestrator using raw diff text (no repo access)."""

    def __init__(self, request: dict, source, language, publisher=None, failure_simulation_llm=None):
        super().__init__(request, source, language, publisher, failure_simulation_llm)

    def _prepare_analysis_inputs(self):
        """Prepare inputs in DIFF_ONLY mode."""
        return InputPreparationPipeline.run(
            request=self.request,
            source=self.source,
            language=self.language,
            mode="DIFF_ONLY",
        )

    def _get_analysis_mode(self) -> AnalysisMode:
        """Get analysis mode for DIFF_ONLY orchestrator."""
        return AnalysisMode.DIFF_ONLY