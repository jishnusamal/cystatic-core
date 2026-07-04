"""
ReviewPipeline — performs LLM review and verdict aggregation.

This pipeline is responsible for:
  - Building reviewer-ready facts from deterministic evidence
  - Running LLM with reviewer-ready facts
  - Validating scenarios
  - Aggregating verdict from LLM and risk patterns

Output: Review

Architecture:
  Deterministic engine -> LlmFacts -> LLM (expert reviewer) -> Review
  The LLM receives facts, not conclusions.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.scenario_validator import score_scenarios, ValidationScore
from core_engine.llm_facts import LlmFacts, LlmFactsBuilder


class Review:
    """Result of the review pipeline.
    
    Attributes:
        failure_simulation: LLM-generated review output.
        validation_score: Scenario validation scores.
        verdict: Aggregated verdict (BLOCK, REVIEW_REQUIRED, APPROVE).
        llm_input_packet: The facts packet passed to the LLM.
    """
    
    def __init__(
        self,
        failure_simulation: dict[str, Any],
        validation_score: ValidationScore,
        verdict: str,
        llm_input_packet: dict[str, Any] | None = None,
    ):
        self.failure_simulation = failure_simulation
        self.validation_score = validation_score
        self.verdict = verdict
        self.llm_input_packet = llm_input_packet
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "failure_simulation": self.failure_simulation,
            "verdict": self.verdict,
            "llm_input_packet": self.llm_input_packet,
        }


class ReviewPipeline:
    """Performs LLM review and verdict aggregation.
    
    This pipeline owns the LLM interaction and verdict logic.
    
    Architecture change:
      The deterministic engine now stops one layer earlier.
      Instead of passing conclusions (scenarios, hypotheses, canonical risks),
      it passes facts (changed symbols, relationships, test coverage, etc.).
      The LLM reasons from facts, not conclusions.
    """
    
    @staticmethod
    def run(
        bundle: EvidenceBundle,
        understanding: Any,  # ChangeUnderstanding - using Any to avoid circular import
        failure_simulation_llm: Any = None,
        inference_result: Any = None,
        compressed_for_llm: dict[str, Any] | None = None,
    ) -> Review:
        """Run the review pipeline.
        
        Architecture:
          Deterministic engine -> LlmFactsBuilder -> LlmFacts -> LLM -> Review
          
          The deterministic engine (EvidenceBundle) is the source of truth.
          LlmFactsBuilder extracts facts (not conclusions) from the bundle.
          The LLM receives facts and reasons from them.
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            understanding: ChangeUnderstanding from ChangeUnderstandingPipeline.
            failure_simulation_llm: Optional LLM instance for review.
            inference_result: Optional InferenceResult from InferencePipeline.
                When omitted, inference is run here (e.g. standalone tests).
            compressed_for_llm: Optional pre-compressed LLM packet (legacy, unused).
            
        Returns:
            Review containing review output and verdict.
        """
        print("Running review pipeline...")
        
        # Step 1: Use inference from orchestrator, or run locally if not provided
        if inference_result is None:
            from core_engine.pipelines.inference import InferencePipeline
            print("Running inference pipeline to generate deterministic scenarios...")
            inference_result = InferencePipeline.run(bundle)
        else:
            print("Using inference result from upstream pipeline...")
        deterministic_scenarios = inference_result.scenarios
        
        # Step 2: Build LlmFacts — facts, not conclusions
        # This is the key architectural change. Instead of passing scenarios,
        # hypotheses, and canonical risks to the LLM, we pass raw facts.
        print("Building LlmFacts from deterministic evidence...")
        repo = ""
        pr_number = 0
        if hasattr(understanding, 'enriched_files') and understanding.enriched_files:
            for f in understanding.enriched_files:
                if isinstance(f, dict):
                    repo = f.get("repo", repo)
                    pr_number = f.get("pr_number", pr_number)
        
        llm_facts = LlmFactsBuilder.build(
            bundle=bundle,
            understanding=understanding,
            repo=repo,
            pr_number=pr_number,
        )
        
        # Pipeline integrity check: fail if no facts were extracted
        has_facts = bool(llm_facts.changed_symbols or llm_facts.behavior_changes or llm_facts.relationships)
        if not has_facts:
            print("WARNING: LlmFacts produced empty packet - skipping LLM")
            return Review(
                failure_simulation=ReviewPipeline._build_empty_facts_fallback(),
                validation_score=score_scenarios({}, {}),
                verdict="REVIEW_REQUIRED",
                llm_input_packet=None,
            )
        
        # Step 3: Build LLM input from facts
        print("Building LLM input from facts...")
        from core_engine.normalized_llm_input_builder import build_normalized_llm_input
        llm_input = build_normalized_llm_input(
            llm_facts=llm_facts,
            repo=repo,
            pr_number=pr_number,
        )
        
        # Step 4: Run LLM if available
        if failure_simulation_llm:
            print("Calling LLM for review...")
            failure_simulation = ReviewPipeline._run_llm(
                llm_input=llm_input,
                failure_simulation_llm=failure_simulation_llm,
            )
        else:
            print("No LLM available, using deterministic scenarios only")
            failure_simulation = ReviewPipeline._build_failure_simulation_from_deterministic(
                deterministic_scenarios=deterministic_scenarios,
            )
        
        # Step 5: Apply deterministic validation scores
        print("Validating scenarios...")
        compressed_ir = inference_result.compression.to_dict() if inference_result.compression else {}
        validation_score = score_scenarios(failure_simulation, compressed_ir)
        
        if validation_score.warnings:
            for warning in validation_score.warnings:
                print(f"Scenario validation warning: {warning}")
        if validation_score.notes:
            for note in validation_score.notes:
                print(f"Scenario validation note: {note}")
        
        # Step 6: Aggregate verdict
        print("Aggregating verdict...")
        risk_patterns = understanding.risk_patterns
        verdict = ReviewPipeline._aggregate_verdict(
            failure_simulation=failure_simulation,
            validation_score=validation_score,
            risk_patterns=risk_patterns,
        )
        
        print(f"Review complete: verdict={verdict}")
        
        return Review(
            failure_simulation=failure_simulation,
            validation_score=validation_score,
            verdict=verdict,
            llm_input_packet=llm_input,
        )
    
    @staticmethod
    def _build_failure_simulation_from_deterministic(
        deterministic_scenarios: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build review output from deterministic scenarios (no LLM).
        
        Used when LLM is not available. Converts deterministic scenarios
        to the new reviewer-ready output format.
        
        Args:
            deterministic_scenarios: Scenarios from deterministic pipeline.
            
        Returns:
            Review output dict in the new format.
        """
        has_scenarios = bool(deterministic_scenarios)
        
        if not has_scenarios:
            return {
                "verdict": "APPROVE",
                "executive_summary": "No significant propagation detected. The change is contained and does not affect downstream systems.",
                "primary_concern": None,
                "additional_observations": [],
                "required_tests": [],
                "reviewer_questions": [],
                "merge_recommendation": "Safe to merge.",
            }
        
        # Build primary concern from the highest-confidence scenario
        top_scenario = deterministic_scenarios[0] if deterministic_scenarios else {}
        primary_concern = None
        if isinstance(top_scenario, dict):
            title = top_scenario.get("title", top_scenario.get("narrative", "Unknown risk"))[:80]
            description = top_scenario.get("description", top_scenario.get("reasoning", ""))
            production_impact = top_scenario.get("production_impact", top_scenario.get("operational_impact", ""))
            causal_chain = top_scenario.get("causal_chain", "")
            supported_by = top_scenario.get("supported_by", [])
            ci_would_catch = top_scenario.get("ci_would_catch", False)
            
            primary_concern = {
                "title": title,
                "why_blocking": description or f"Change in {', '.join(supported_by[:3]) if supported_by else 'affected symbols'} introduces production risk",
                "execution_path": causal_chain or f"{' → '.join(supported_by[:4]) if supported_by else 'Unknown execution path'}",
                "customer_or_business_impact": production_impact or "Potential downstream impact",
                "why_existing_tests_miss_it": "Existing tests do not cover this execution path" if not ci_would_catch else "Covered by existing CI",
                "confidence_rationale": f"Deterministic analysis identified this as the highest-risk scenario (confidence: {top_scenario.get('confidence', 0):.2f})",
                "required_validation": "Integration test covering the identified execution path" if not ci_would_catch else "Existing CI coverage is sufficient",
            }
        
        # Build additional observations from remaining scenarios
        additional_observations = []
        for scenario in deterministic_scenarios[1:4]:
            if not isinstance(scenario, dict):
                continue
            additional_observations.append({
                "title": scenario.get("title", scenario.get("narrative", "Additional observation"))[:80],
                "observation": scenario.get("reasoning", scenario.get("description", "")),
                "symbols": scenario.get("supported_by", []),
            })
        
        # Build required tests
        required_tests = []
        for s in deterministic_scenarios[:3]:
            if not s.get("ci_would_catch", False):
                title = s.get("title", "Change")
                required_tests.append(f"Integration test for {title[:60]}")
        
        # Build reviewer questions
        reviewer_questions = []
        for s in deterministic_scenarios[:2]:
            title = s.get("title", "This change")
            causal = s.get("causal_chain", "")
            if causal:
                reviewer_questions.append(f"Has the {causal[:80]} path been verified under production-like load?")
            else:
                reviewer_questions.append(f"Has {title[:60]} been tested in the context of downstream consumers?")
        
        # Build merge recommendation
        merge_recommendation = "Requires review before merge."
        if primary_concern:
            merge_recommendation = f"Blocked by: {primary_concern['title']}"
        
        return {
            "verdict": "BLOCK" if primary_concern else "REVIEW_REQUIRED",
            "executive_summary": ReviewPipeline._build_executive_summary(deterministic_scenarios),
            "primary_concern": primary_concern,
            "additional_observations": additional_observations,
            "required_tests": required_tests[:5],
            "reviewer_questions": reviewer_questions[:5],
            "merge_recommendation": merge_recommendation,
        }
    
    @staticmethod
    def _build_executive_summary(scenarios: list[dict]) -> str:
        """Build executive summary from deterministic scenarios."""
        if not scenarios:
            return "No significant risk detected."
        
        top = scenarios[0]
        title = top.get("title", top.get("narrative", "Change"))
        impact = top.get("production_impact", top.get("operational_impact", ""))
        
        if impact:
            return f"{title}: {impact[:200]}"
        
        return f"{len(scenarios)} concerns identified. The highest-confidence risk involves {title}."
    
    @staticmethod
    def _run_llm(
        llm_input: dict[str, Any],
        failure_simulation_llm: Any,
    ) -> dict[str, Any]:
        """Call LLM with reviewer-ready facts.
        
        The LLM receives only deterministic facts from normalized_llm_input_builder.
        It does NOT receive internal implementation artifacts.
        
        Args:
            llm_input: Deterministic facts from normalized_llm_input_builder.
            failure_simulation_llm: LLM instance.
            
        Returns:
            Review output dict from LLM.
        """
        output = failure_simulation_llm.generate(
            llm_input=llm_input,
        )
        failure_simulation = output.model_dump()
        
        # Sanitize LLM output
        failure_simulation = ReviewPipeline._sanitize_llm_output(failure_simulation)
        
        return failure_simulation
    
    @staticmethod
    def _aggregate_verdict(
        failure_simulation: dict,
        validation_score: ValidationScore | None = None,
        risk_patterns: list | None = None,
    ) -> str:
        """Aggregate verdict from LLM output and risk patterns.
        
        Core signal: LLM assessment with contextual findings.
        Secondary signal: risk patterns.
        """
        if not isinstance(failure_simulation, dict):
            failure_simulation = ReviewPipeline._default_failure_simulation()
        
        llm_verdict = failure_simulation.get("verdict", "")
        
        # Accept LLM verdict if present
        if llm_verdict:
            return llm_verdict
        
        # Fall back to risk pattern-based verdict
        pr_risk_level = "LOW"
        if risk_patterns:
            pr_risk_level = "MEDIUM" if any(getattr(rp, 'severity', 'LOW') == 'HIGH' for rp in risk_patterns) else "LOW"
        
        return ReviewPipeline._get_verdict(pr_risk_level, risk_patterns=risk_patterns)
    
    @staticmethod
    def _build_empty_facts_fallback() -> dict:
        """Build fallback when LlmFacts produces empty packet.
        
        This prevents the LLM from inventing 'no findings' when the
        deterministic engine clearly produced evidence.
        """
        return {
            "verdict": "REVIEW_REQUIRED",
            "executive_summary": "Unable to extract deterministic facts from evidence. Manual review required.",
            "primary_concern": {
                "title": "LlmFacts builder produced empty packet",
                "why_blocking": "The deterministic engine produced evidence but the LlmFacts builder failed to extract any facts. This indicates a pipeline integrity issue.",
                "execution_path": "EvidenceBundle → LlmFactsBuilder → ReviewPipeline",
                "customer_or_business_impact": "Unknown - fact extraction failure prevents risk assessment",
                "why_existing_tests_miss_it": "N/A - pipeline integrity issue",
                "confidence_rationale": "LlmFacts produced 0 changed symbols, 0 behavior changes, and 0 relationships despite evidence being present",
                "required_validation": "Investigate LlmFacts builder failure and review deterministic evidence manually",
            },
            "additional_observations": [],
            "required_tests": ["Manual review of LlmFacts builder logs"],
            "reviewer_questions": ["Why did the LlmFacts builder fail to extract facts from the evidence bundle?"],
            "merge_recommendation": "Blocked by fact extraction failure - requires manual investigation",
        }

    @staticmethod
    def _default_failure_simulation() -> dict:
        return {
            "verdict": "APPROVE",
            "executive_summary": "",
            "primary_concern": None,
            "additional_observations": [],
            "required_tests": [],
            "reviewer_questions": [],
            "merge_recommendation": "",
        }
    
    @staticmethod
    def _sanitize_llm_output(raw_output: dict) -> dict:
        if not isinstance(raw_output, dict):
            return ReviewPipeline._default_failure_simulation()
        
        sanitized = {}
        expected_keys = {
            "verdict",
            "executive_summary",
            "primary_concern",
            "additional_observations",
            "required_tests",
            "reviewer_questions",
            "merge_recommendation",
        }
        
        for key, value in raw_output.items():
            try:
                clean_key = key.encode().decode('unicode_escape')
            except (UnicodeDecodeError, AttributeError):
                clean_key = key
            
            clean_key = clean_key.strip().strip('"\'').strip()
            
            matched_key = None
            for expected in expected_keys:
                if clean_key == expected or clean_key.replace(" ", "_").lower() == expected.lower():
                    matched_key = expected
                    break
            
            if matched_key:
                sanitized[matched_key] = value
            else:
                sanitized[clean_key] = value
        
        return sanitized
    
    @staticmethod
    def _get_verdict(pr_risk_level: str, risk_patterns: list | None = None) -> str:
        has_risk_patterns = bool(risk_patterns)
        if has_risk_patterns:
            if "HIGH" in pr_risk_level:
                return "BLOCK"
            return "REVIEW_REQUIRED"
        if "HIGH" in pr_risk_level:
            return "REVIEW_REQUIRED"
        if "MEDIUM" in pr_risk_level:
            return "REVIEW_REQUIRED"
        return "APPROVE"