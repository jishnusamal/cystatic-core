"""
Evidence-Driven Orchestrator

New architecture that separates facts from predictions.
Replaces graph-centric approach with evidence-driven reasoning pipeline.

Pipeline:
PR/Diff → Language Adapter → Analysis Context → Evidence Analyzer Registry →
Evidence Bundle → Impact Hypothesis Generator → Failure Scenario Generator →
LLM Narrative Generation → PR Review Output
"""
from __future__ import annotations

from typing import Any
from schemas import AnalyzeRequest
from jinja2 import Environment, FileSystemLoader, Template  # pyright: ignore[reportMissingImports]
from api.models import persist_analysis_result
from language_adapters.python.python_adapter import AnalysisMode

from core_engine.analysers.registry import AnalyzerRegistry
from core_engine.analysers.changed_symbols import ChangedSymbolAnalyzer
from core_engine.analysers.side_effects import SideEffectAnalyzer
from core_engine.analysers.business_objects import BusinessObjectAnalyzer
from core_engine.analysers.risk_anchors import RiskAnchorAnalyzer
from core_engine.analysers.database_relationships import DatabaseRelationshipAnalyzer
from core_engine.analysers.event_relationships import EventRelationshipAnalyzer
from core_engine.analysers.constraints import ConstraintAnalyzer
from core_engine.analysers.domain_relationships import DomainRelationshipAnalyzer
from core_engine.analysers.ownership import OwnershipAnalyzer
from core_engine.analysers.endpoint_relationships import EndpointRelationshipAnalyzer
from core_engine.analysers.naming_similarity import NamingSimilarityAnalyzer
from core_engine.analysers.import_relationships import ImportRelationshipAnalyzer

from core_engine.hypothesis.generator import HypothesisGenerator
from core_engine.scenarios.generator import FailureScenarioGenerator

from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.models.impact_hypothesis import ImpactHypothesis
from core_engine.models.failure_scenario import FailureScenario


class EvidenceDrivenOrchestrator:
    """Evidence-driven orchestrator using the new analysis pipeline.
    
    This orchestrator:
    - Builds AnalysisContext once
    - Executes all analyzers through the registry
    - Generates EvidenceBundle (deterministic facts)
    - Generates ImpactHypotheses (probabilistic)
    - Generates FailureScenarios (concrete failures)
    - Never uses causal graphs for propagation
    """
    
    def __init__(
        self,
        request: AnalyzeRequest,
        source: Any,
        language: Any,
        publisher: Any = None,
        failure_simulation_llm: Any = None,
    ):
        self.request = request
        self.source = source
        self.language = language
        self.publisher = publisher
        self.failure_simulation_llm = failure_simulation_llm
    
    def run_pr_analysis(self) -> dict[str, Any]:
        """Run the evidence-driven PR analysis pipeline.
        
        Returns:
            Analysis result dictionary.
        """
        # Stage 1: Language Understanding
        # (Already done by language adapter before orchestrator is called)
        
        # Stage 2: Build Analysis Context
        context = self._build_analysis_context()
        
        # Stage 3: Execute Analyzer Registry
        evidence_bundle = self._run_analyzers(context)
        
        # Stage 4: Generate Impact Hypotheses
        hypotheses = self._generate_hypotheses(evidence_bundle)
        
        # Stage 5: Generate Failure Scenarios
        scenarios = self._generate_scenarios(hypotheses)
        
        # Stage 6: Generate LLM Narrative (if LLM available)
        llm_narrative = self._generate_llm_narrative(evidence_bundle, hypotheses, scenarios)
        
        # Stage 7: Render Comment
        comment = self._render_comment(evidence_bundle, hypotheses, scenarios, llm_narrative)
        
        # Stage 8: Build and return result
        result = self._build_result(
            evidence_bundle=evidence_bundle,
            hypotheses=hypotheses,
            scenarios=scenarios,
            llm_narrative=llm_narrative,
            comment=comment,
        )
        
        return result
    
    def _build_analysis_context(self) -> Any:
        """Build the analysis context from the PR.
        
        Returns:
            AnalysisContext object.
        """
        from core_engine.analysers.analysis_context import AnalysisContext
        
        # Fetch diff
        diff_ir = self.source.fetch_diff(self.request.repo, self.request.pr_number)
        
        # Apply file exclusions
        from core_engine.file_exclusion import FileExclusionService
        file_exclusion = FileExclusionService()
        kept_files = []
        for file in diff_ir.files:
            file_path = getattr(file, "file_path", "")
            matched = file_exclusion.get_exclusion_match(file_path)
            if not matched:
                kept_files.append(file)
        diff_ir.files = kept_files
        
        # Extract changed files
        files = self.language.extract_changed_files(diff_ir) or []
        
        # Build context components
        enriched_files = []
        file_snapshots = {}
        asts = {}
        
        # Get head SHA for full file snapshots
        sha = self.source.get_head_sha(self.request.repo, self.request.pr_number)
        
        for file in files:
            file_path = file["file_path"]
            
            # Fetch full file snapshot
            try:
                snapshot = self.source.fetch_file_at_sha(
                    repo=self.request.repo,
                    file_path=file_path,
                    sha=sha,
                )
                file_snapshots[file_path] = snapshot.content
            except Exception:
                file_snapshots[file_path] = ""
            
            # Extract language-specific information
            changed_functions = self.language.extract_changed_functions(
                file=file,
                mode=AnalysisMode.FULL_FILE,
                content=file_snapshots[file_path],
            )
            keyword_signals = self.language.extract_keyword_signals_from_diff(file=file)
            endpoints = self.language.extract_endpoints(
                file_path=file_path,
                content=file_snapshots[file_path],
            )
            
            # Build enriched file
            changed_function_names = {fn.name for fn in changed_functions}
            impacted_endpoints = [
                ep for ep in endpoints if ep["function"] in changed_function_names
            ]
            
            enriched_file = {
                "file_path": file_path,
                "lines_changed": file.get("lines_changed", 0),
                "hunks": getattr(file, "hunks", []),
                "total_functions_changed": len(changed_functions),
                "total_endpoints": len(impacted_endpoints),
                "total_keyword_signals": len(keyword_signals),
                "changed_functions": changed_functions,
                "endpoints": impacted_endpoints,
                "keyword_signals": keyword_signals,
            }
            enriched_files.append(enriched_file)
        
        # Detect risk patterns
        from core_engine.risk_pattern_detector import RiskPatternDetector
        risk_detector = RiskPatternDetector()
        risk_patterns = risk_detector.detect(enriched_files)
        
        # Build and return context
        context = AnalysisContext(
            diff=diff_ir.model_dump() if hasattr(diff_ir, "model_dump") else {},
            changed_files=[f["file_path"] for f in files],
            asts=asts,
            repo_metadata={
                "repo": self.request.repo,
                "pr_number": self.request.pr_number,
            },
            file_snapshots=file_snapshots,
            language_adapter=self.language,
            pr_metadata={
                "repo": self.request.repo,
                "pr_number": self.request.pr_number,
            },
            configuration={},
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
        )
        
        return context
    
    def _run_analyzers(self, context: Any) -> EvidenceBundle:
        """Execute all analyzers through the registry.
        
        Args:
            context: AnalysisContext to analyze.
            
        Returns:
            EvidenceBundle with all evidence from all analyzers.
        """
        # Create registry
        registry = AnalyzerRegistry()
        
        # Register all analyzers
        registry.register(ChangedSymbolAnalyzer())
        registry.register(SideEffectAnalyzer())
        registry.register(BusinessObjectAnalyzer())
        registry.register(RiskAnchorAnalyzer())
        registry.register(DatabaseRelationshipAnalyzer())
        registry.register(EventRelationshipAnalyzer())
        registry.register(ConstraintAnalyzer())
        registry.register(DomainRelationshipAnalyzer())
        registry.register(OwnershipAnalyzer())
        registry.register(EndpointRelationshipAnalyzer())
        registry.register(NamingSimilarityAnalyzer())
        registry.register(ImportRelationshipAnalyzer())
        
        # Execute all analyzers
        evidence_bundle = registry.analyze_all(context)
        
        return evidence_bundle
    
    def _generate_hypotheses(self, evidence_bundle: EvidenceBundle) -> list[ImpactHypothesis]:
        """Generate impact hypotheses from evidence bundle.
        
        Args:
            evidence_bundle: The deterministic evidence bundle.
            
        Returns:
            List of probabilistic impact hypotheses.
        """
        generator = HypothesisGenerator()
        hypotheses = generator.generate(evidence_bundle)
        return hypotheses
    
    def _generate_scenarios(
        self,
        hypotheses: list[ImpactHypothesis],
    ) -> list[FailureScenario]:
        """Generate failure scenarios from hypotheses.
        
        Args:
            hypotheses: List of probabilistic impact hypotheses.
            
        Returns:
            List of concrete failure scenarios.
        """
        generator = FailureScenarioGenerator()
        scenarios = generator.generate(hypotheses)
        return scenarios
    
    def _generate_llm_narrative(
        self,
        evidence_bundle: EvidenceBundle,
        hypotheses: list[ImpactHypothesis],
        scenarios: list[FailureScenario],
    ) -> dict[str, Any] | None:
        """Generate LLM narrative if LLM is available.
        
        Args:
            evidence_bundle: The evidence bundle.
            hypotheses: List of impact hypotheses.
            scenarios: List of failure scenarios.
            
        Returns:
            LLM narrative dict or None if LLM not available.
        """
        if not self.failure_simulation_llm:
            return None
        
        # Build compressed packet for LLM
        compressed = self._compress_for_llm(evidence_bundle, hypotheses, scenarios)
        
        # Call LLM
        output = self.failure_simulation_llm.generate(**compressed)
        
        # Return as dict
        return output.model_dump() if hasattr(output, "model_dump") else output
    
    def _compress_for_llm(
        self,
        evidence_bundle: EvidenceBundle,
        hypotheses: list[ImpactHypothesis],
        scenarios: list[FailureScenario],
    ) -> dict[str, Any]:
        """Compress evidence and hypotheses for LLM consumption.
        
        Args:
            evidence_bundle: The evidence bundle.
            hypotheses: List of impact hypotheses.
            scenarios: List of failure scenarios.
            
        Returns:
            Compressed packet for LLM.
        """
        return {
            "repo": self.request.repo,
            "pr_number": self.request.pr_number,
            "evidence_summary": {
                "changed_symbols_count": len(evidence_bundle.changed_symbols),
                "risk_anchors_count": len(evidence_bundle.risk_anchors),
                "impact_evidence_count": len(evidence_bundle.impact_evidence),
                "side_effects_count": len(evidence_bundle.side_effects),
                "constraints_count": len(evidence_bundle.constraints),
                "business_objects": [bo.get("name") for bo in evidence_bundle.business_objects],
                "domains": evidence_bundle.domains,
            },
            "hypotheses": [
                {
                    "source": h.source_symbol,
                    "target": h.target_symbol,
                    "impact_type": h.impact_type,
                    "confidence": h.confidence,
                    "description": h.description,
                }
                for h in hypotheses[:10]  # Top 10
            ],
            "scenarios": [
                {
                    "title": s.title,
                    "confidence": s.confidence,
                    "impact_type": s.impact_type,
                    "risk_level": s.merge_risk_level,
                    "description": s.description,
                }
                for s in scenarios[:5]  # Top 5
            ],
        }
    
    def _render_comment(
        self,
        evidence_bundle: EvidenceBundle,
        hypotheses: list[ImpactHypothesis],
        scenarios: list[FailureScenario],
        llm_narrative: dict[str, Any] | None,
    ) -> str:
        """Render PR comment from analysis results.
        
        Args:
            evidence_bundle: The evidence bundle.
            hypotheses: List of impact hypotheses.
            scenarios: List of failure scenarios.
            llm_narrative: Optional LLM narrative.
            
        Returns:
            Rendered comment string.
        """
        env = Environment(loader=FileSystemLoader("templates"))
        
        try:
            template = env.get_template("github/pr_comment.md.j2")
        except Exception:
            # Fallback to simple comment
            return self._render_simple_comment(evidence_bundle, hypotheses, scenarios)
        
        # Build result dict for template
        result = {
            "verdict": self._determine_verdict(scenarios),
            "failure_simulation": {
                "failure_scenarios": [
                    {
                        "title": s.title,
                        "confidence": s.confidence,
                        "merge_risk_level": s.merge_risk_level,
                        "reasoning": s.reasoning,
                        "causal_chain": s.causal_chain,
                        "failure_class": s.failure_class,
                    }
                    for s in scenarios
                ],
                "verdict_rationale": llm_narrative.get("verdict_rationale", "") if llm_narrative else "",
            },
        }
        
        return template.render(**result)
    
    def _render_simple_comment(
        self,
        evidence_bundle: EvidenceBundle,
        hypotheses: list[ImpactHypothesis],
        scenarios: list[FailureScenario],
    ) -> str:
        """Render a simple comment as fallback.
        
        Args:
            evidence_bundle: The evidence bundle.
            hypotheses: List of impact hypotheses.
            scenarios: List of failure scenarios.
            
        Returns:
            Simple comment string.
        """
        lines = ["## Cystatic Analysis Results\n"]
        
        # Summary
        lines.append(f"### Summary")
        lines.append(f"- Changed symbols: {len(evidence_bundle.changed_symbols)}")
        lines.append(f"- Risk anchors: {len(evidence_bundle.risk_anchors)}")
        lines.append(f"- Impact evidence: {len(evidence_bundle.impact_evidence)}")
        lines.append(f"- Hypotheses: {len(hypotheses)}")
        lines.append(f"- Scenarios: {len(scenarios)}\n")
        
        # Top scenarios
        if scenarios:
            lines.append("### Top Failure Scenarios\n")
            for i, scenario in enumerate(scenarios[:5], 1):
                lines.append(f"{i}. **{scenario.title}** (confidence: {scenario.confidence:.2f}, risk: {scenario.merge_risk_level})")
                lines.append(f"   - {scenario.description}\n")
        
        return "\n".join(lines)
    
    def _determine_verdict(self, scenarios: list[FailureScenario]) -> str:
        """Determine overall verdict from scenarios.
        
        Args:
            scenarios: List of failure scenarios.
            
        Returns:
            Verdict string.
        """
        if not scenarios:
            return "SAFE"
        
        # Check for high-risk scenarios
        high_risk = any(s.merge_risk_level == "HIGH" for s in scenarios)
        medium_risk = any(s.merge_risk_level == "MEDIUM" for s in scenarios)
        
        if high_risk:
            return "BLOCK_REVIEW"
        elif medium_risk:
            return "REVIEW_REQUIRED"
        else:
            return "REVIEW_RECOMMENDED"
    
    def _build_result(
        self,
        evidence_bundle: EvidenceBundle,
        hypotheses: list[ImpactHypothesis],
        scenarios: list[FailureScenario],
        llm_narrative: dict[str, Any] | None,
        comment: str,
    ) -> dict[str, Any]:
        """Build the final result dictionary.
        
        Args:
            evidence_bundle: The evidence bundle.
            hypotheses: List of impact hypotheses.
            scenarios: List of failure scenarios.
            llm_narrative: Optional LLM narrative.
            comment: Rendered comment.
            
        Returns:
            Result dictionary.
        """
        return {
            "repo": self.request.repo,
            "pr_number": self.request.pr_number,
            "verdict": self._determine_verdict(scenarios),
            "evidence_bundle": evidence_bundle.model_dump() if hasattr(evidence_bundle, "model_dump") else {},
            "hypotheses": [h.model_dump() if hasattr(h, "model_dump") else h for h in hypotheses],
            "scenarios": [s.model_dump() if hasattr(s, "model_dump") else s for s in scenarios],
            "llm_narrative": llm_narrative,
            "generated_comment": comment,
        }
    
    def publish_comments(self, result: dict[str, Any]) -> None:
        """Publish comments to the PR.
        
        Args:
            result: Analysis result dictionary.
        """
        comment = result.get("generated_comment", "")
        print(f"Publishing comment to {self.request.repo} PR #{self.request.pr_number}:\n{comment}")
    
    async def log_run(self, result: dict[str, Any]) -> None:
        """Log the analysis run.
        
        Args:
            result: Analysis result dictionary.
        """
        await persist_analysis_result(result)
        print(f"Logged analysis run for {self.request.repo} PR #{self.request.pr_number}")