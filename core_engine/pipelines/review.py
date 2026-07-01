"""
ReviewPipeline — performs LLM review and verdict aggregation.

This pipeline is responsible for:
  - Compressing evidence for LLM consumption
  - Running LLM with causal context
  - Validating scenarios
  - Aggregating verdict from LLM and risk patterns

Output: Review
"""
from __future__ import annotations

from typing import Any

from core_engine.llm_packet_compressor import build_llm_packet
from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.risk_compressor import compress_risk_hypotheses
from core_engine.scenario_validator import score_scenarios, ValidationScore


class Review:
    """Result of the review pipeline.
    
    Attributes:
        failure_simulation: LLM-generated failure simulation.
        validation_score: Scenario validation scores.
        verdict: Aggregated verdict (BLOCK_REVIEW, REVIEW_REQUIRED, etc.).
    """
    
    def __init__(
        self,
        failure_simulation: dict[str, Any],
        validation_score: ValidationScore,
        verdict: str,
    ):
        self.failure_simulation = failure_simulation
        self.validation_score = validation_score
        self.verdict = verdict
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "failure_simulation": self.failure_simulation,
            "verdict": self.verdict,
        }


class ReviewPipeline:
    """Performs LLM review and verdict aggregation.
    
    This pipeline owns the LLM interaction and verdict logic.
    """
    
    @staticmethod
    def run(
        bundle: EvidenceBundle,
        understanding: Any,  # ChangeUnderstanding - using Any to avoid circular import
        failure_simulation_llm: Any = None,
        compressed_for_llm: dict[str, Any] | None = None,
    ) -> Review:
        """Run the review pipeline.
        
        Hybrid deterministic + LLM architecture:
        - Deterministic engine: fact generator (evidence, hypotheses, scenarios)
        - LLM: expert reviewer (validates, ranks, explains, challenges)
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            understanding: ChangeUnderstanding from ChangeUnderstandingPipeline.
            failure_simulation_llm: Optional LLM instance for failure simulation.
            compressed_for_llm: Optional pre-compressed LLM packet.
            
        Returns:
            Review containing failure simulation and verdict.
        """
        print("Running review pipeline...")
        
        # Step 1: Build deterministic scenarios from inference pipeline
        from core_engine.pipelines.inference import InferencePipeline
        print("Running inference pipeline to generate deterministic scenarios...")
        inference_result = InferencePipeline.run(bundle)
        deterministic_scenarios = inference_result.scenarios
        
        # Step 2: Build LLM packet with evidence graph format
        print("Building LLM packet with evidence graph...")
        # Build the parameters that build_llm_packet actually accepts
        changed_symbols_list = [cs.symbol for cs in bundle.changed_symbols]
        influence = []
        for cs in bundle.changed_symbols:
            influence.append({
                "symbol": cs.symbol,
                "domain": "general",
                "influence_score": 0.5,
            })
        impact_evidence = [ev.model_dump() for ev in bundle.impact_evidence]
        risk_zones = bundle.domains if bundle.domains else ["general"]
        
        # Convert business objects to dicts
        business_objects = []
        for bo in bundle.business_objects:
            if hasattr(bo, "model_dump"):
                business_objects.append(bo.model_dump())
            elif isinstance(bo, dict):
                business_objects.append(bo)
        
        # Convert constraints to dicts
        constraints = []
        for c in bundle.constraints:
            if hasattr(c, "model_dump"):
                constraints.append(c.model_dump())
            elif isinstance(c, dict):
                constraints.append(c)
        
        # Extract additional context for evidence graph
        entry_points = [ep.symbol if hasattr(ep, 'symbol') else str(ep) for ep in understanding.entry_points_affected] if understanding.entry_points_affected else []
        
        side_effects = [se.model_dump() if hasattr(se, "model_dump") else se for se in bundle.side_effects]
        
        transaction_boundaries = []
        for c in bundle.constraints:
            if hasattr(c, 'constraint_type'):
                if 'transaction' in c.constraint_type.value.lower():
                    transaction_boundaries.append(c.symbol)
            elif isinstance(c, dict) and 'transaction' in str(c.get('constraint_type', '')).lower():
                transaction_boundaries.append(c.get('symbol', ''))
        
        external_dependencies = []
        for se in bundle.side_effects:
            if hasattr(se, 'effect_type'):
                if 'external' in se.effect_type.lower() or 'http' in se.effect_type.lower():
                    external_dependencies.append(se.symbol)
            elif isinstance(se, dict) and ('external' in str(se.get('effect_type', '')).lower() or 'http' in str(se.get('effect_type', '')).lower()):
                external_dependencies.append(se.get('symbol', ''))
        
        compressed_for_llm = build_llm_packet(
            change_influence=influence,
            impact_evidence=impact_evidence,
            risk_zones=risk_zones,
            changed_symbols=changed_symbols_list,
            deterministic_scenarios=deterministic_scenarios,
            business_objects=business_objects,
            domains=bundle.domains,
            constraints=constraints,
            entry_points=entry_points,
            side_effects=side_effects,
            transaction_boundaries=transaction_boundaries,
            external_dependencies=external_dependencies,
        )
        
        # Step 3: Build risk hypotheses for LLM context (legacy support)
        from core_engine.failure_archetype_engine import build_risk_hypotheses
        from core_engine.impact_evidence import synthesize_evidence_summary, ImpactEvidence as OldImpactEvidence
        
        # Convert Pydantic ImpactEvidence to old dataclass format for synthesize_evidence_summary
        old_style_evidence = []
        for ev in bundle.impact_evidence:
            old_style_evidence.append(OldImpactEvidence(
                source_symbol=ev.source.name if hasattr(ev.source, 'name') else str(ev.source),
                target_symbol=ev.target.name if hasattr(ev.target, 'name') else str(ev.target),
                evidence_type=ev.evidence_type.value if hasattr(ev.evidence_type, 'value') else str(ev.evidence_type),
                confidence=ev.confidence,
                explanation=ev.explanation,
                metadata=ev.metadata,
            ))
        evidence_summary = synthesize_evidence_summary(old_style_evidence)
        # Convert EvidenceSummary dataclass objects to dicts for build_risk_hypotheses
        evidence_summary_dicts = [es.to_dict() for es in evidence_summary]
        risk_hypotheses = build_risk_hypotheses(
            change_influence=[],  # Not needed for LLM context
            evidence_summary=evidence_summary_dicts,
        )
        
        # Compress risk hypotheses
        compressed_risk_hypotheses = compress_risk_hypotheses(
            risk_hypotheses=risk_hypotheses,
            top_n=3,
            compress_for_llm=True,
        )
        compressed_for_llm["compressed_risk_hypotheses"] = compressed_risk_hypotheses
        
        # Step 4: Run LLM if available
        if failure_simulation_llm:
            print("Calling LLM for validation and ranking...")
            failure_simulation = ReviewPipeline._run_llm(
                compressed_for_llm=compressed_for_llm,
                bundle=bundle,
                failure_simulation_llm=failure_simulation_llm,
            )
        else:
            print("No LLM available, using deterministic scenarios only")
            failure_simulation = ReviewPipeline._build_failure_simulation_from_deterministic(
                deterministic_scenarios=deterministic_scenarios,
            )
        
        # Step 5: Apply deterministic validation scores
        print("Validating scenarios...")
        validation_score = score_scenarios(failure_simulation, compressed_for_llm)
        
        if validation_score.warnings:
            for warning in validation_score.warnings:
                print(f"Scenario validation warning: {warning}")
        if validation_score.notes:
            for note in validation_score.notes:
                print(f"Scenario validation note: {note}")
        
        # Step 6: Apply confidence adjustments from deterministic validation
        for score in validation_score.scenarios:
            if score.scenario_index < len(failure_simulation.get("failure_scenarios", [])):
                scenario = failure_simulation["failure_scenarios"][score.scenario_index]
                orig_confidence = scenario.get("confidence", 0.7)
                scenario["confidence"] = round(orig_confidence * score.confidence_adjustment, 3)
                if score.issues:
                    scenario["reasoning"] = (
                        scenario.get("reasoning", "") +
                        f"\n[Validation: {'; '.join(score.issues)}]"
                    )
        
        # Step 7: Aggregate verdict
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
        )
    
    @staticmethod
    def _build_failure_simulation_from_deterministic(
        deterministic_scenarios: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build failure simulation dict from deterministic scenarios (no LLM).
        
        Used when LLM is not available. Converts deterministic scenarios
        to the expected output format.
        
        Args:
            deterministic_scenarios: Scenarios from deterministic pipeline.
            
        Returns:
            Failure simulation dict.
        """
        failure_scenarios = []
        for scenario in deterministic_scenarios:
            if not isinstance(scenario, dict):
                continue
            failure_scenarios.append({
                "title": scenario.get("title", scenario.get("narrative", "Unknown scenario")[:100]),
                "trigger": scenario.get("description", "Deterministic scenario"),
                "evidence_type": "inferred",
                "production_impact": scenario.get("operational_impact", scenario.get("production_impact", "")),
                "confidence": scenario.get("confidence", 0.5),
                "causal_chain": scenario.get("causal_chain", ""),
                "failure_class": scenario.get("failure_class", ""),
                "first_observable_signal": scenario.get("first_observable_signal", "unknown"),
                "silent_failure": scenario.get("silent_failure", True),
                "ci_would_catch": scenario.get("ci_would_catch", False),
                "merge_risk_level": scenario.get("merge_risk_level", "MEDIUM"),
                "supported_by": scenario.get("supported_by", []),
                "reasoning": scenario.get("reasoning", ""),
            })
        
        return {
            "failure_scenarios": failure_scenarios[:5],
            "hidden_impact_chain": [],
            "checked_risk_areas": [],
            "missing_critical_tests": [],
            "broken_assumptions": [],
            "silent_failure_summary": "",
            "merge_risk_statement": "",
            "verdict_rationale": "",
            "verdict": "REVIEW_REQUIRED" if failure_scenarios else "NO_SIGNIFICANT_PROPAGATION_FOUND",
            "final_question": "",
            "system_behavior_deltas": [],
            "matched_failure_templates": [],
            # New fields (empty when no LLM)
            "scenario_validations": [],
            "scenario_rankings": [],
            "evidence_challenges": [],
            "missing_evidence": [],
            "impact_explanations": [],
            "executive_summary": "",
            "top_risks": [],
        }
    
    @staticmethod
    def _run_llm(
        compressed_for_llm: dict[str, Any],
        bundle: EvidenceBundle,
        failure_simulation_llm: Any,
    ) -> dict[str, Any]:
        """Call LLM with the evidence-driven LLM payload.
        
        Hybrid architecture: LLM validates and ranks deterministic scenarios.
        
        Args:
            compressed_for_llm: Compressed IR for the LLM (with evidence graph).
            bundle: EvidenceBundle with all evidence.
            failure_simulation_llm: LLM instance.
            
        Returns:
            Failure simulation dict from LLM with validation/ranking.
        """
        # Build changed symbols list
        changed_symbols = [cs.symbol for cs in bundle.changed_symbols]
        
        # Build change influence (simplified)
        change_influence = []
        for cs in bundle.changed_symbols:
            change_influence.append({
                "symbol": cs.symbol,
                "domain": "general",
                "influence_score": 0.5,
            })
        
        # Build impact evidence
        impact_evidence = [ev.model_dump() for ev in bundle.impact_evidence]
        
        # Build risk zones from domains
        risk_zones = bundle.domains if bundle.domains else ["general"]
        
        # Call LLM with evidence graph scenarios (if available)
        # The LLM will validate and rank the deterministic scenarios
        output = failure_simulation_llm.generate(
            repo=compressed_for_llm.get("repo", ""),
            pr_number=compressed_for_llm.get("pr_number", 0),
            change_influence=change_influence,
            impact_evidence=impact_evidence,
            risk_zones=risk_zones,
            changed_symbols=changed_symbols,
            evidence_summary=compressed_for_llm.get("compressed_risk_hypotheses"),
        )
        failure_simulation = output.model_dump()
        
        # Sanitize LLM output
        failure_simulation = ReviewPipeline._sanitize_llm_output(failure_simulation)
        
        # Ensure deterministic scenarios are preserved (LLM may not return them)
        if "failure_scenarios" not in failure_simulation or not failure_simulation["failure_scenarios"]:
            # LLM didn't return scenarios, use deterministic ones
            deterministic_scenarios = compressed_for_llm.get("scenarios", [])
            if deterministic_scenarios:
                failure_simulation["failure_scenarios"] = [
                    {
                        "title": s.get("title", "Unknown"),
                        "trigger": s.get("production_impact", ""),
                        "evidence_type": "inferred",
                        "production_impact": s.get("production_impact", ""),
                        "confidence": s.get("confidence", 0.5),
                        "causal_chain": " → ".join(s.get("causal_chain", [])) if isinstance(s.get("causal_chain"), list) else s.get("causal_chain", ""),
                        "failure_class": s.get("failure_class", ""),
                        "first_observable_signal": "See validation",
                        "silent_failure": s.get("silent_failure", True),
                        "ci_would_catch": s.get("ci_would_catch", False),
                        "merge_risk_level": s.get("merge_risk_level", "MEDIUM"),
                        "supported_by": [],
                        "reasoning": "Deterministic scenario (LLM validation only)",
                    }
                    for s in deterministic_scenarios[:5]
                ]
        
        return failure_simulation
    
    @staticmethod
    def _aggregate_verdict(
        failure_simulation: dict,
        validation_score: ValidationScore | None = None,
        risk_patterns: list | None = None,
    ) -> str:
        """Aggregate verdict from LLM output and risk patterns.
        
        Core signal: LLM assessment with causal context.
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
    def _default_failure_simulation() -> dict:
        return {
            "failure_scenarios": [],
            "hidden_impact_chain": [],
            "checked_risk_areas": [],
            "missing_critical_tests": [],
            "broken_assumptions": [],
            "silent_failure_summary": "",
            "merge_risk_statement": "",
            "verdict_rationale": "",
            "verdict": "NO_SIGNIFICANT_PROPAGATION_FOUND",
            "final_question": "",
            "system_behavior_deltas": [],
            "matched_failure_templates": [],
        }
    
    @staticmethod
    def _sanitize_llm_output(raw_output: dict) -> dict:
        if not isinstance(raw_output, dict):
            return ReviewPipeline._default_failure_simulation()
        
        sanitized = {}
        expected_keys = {
            "failure_scenarios",
            "hidden_impact_chain",
            "checked_risk_areas",
            "missing_critical_tests",
            "broken_assumptions",
            "silent_failure_summary",
            "merge_risk_statement",
            "verdict_rationale",
            "verdict",
            "final_question",
            "system_behavior_deltas",
            "matched_failure_templates",
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
                return "BLOCK_REVIEW"
            return "REVIEW_REQUIRED"
        if "HIGH" in pr_risk_level:
            return "REVIEW_RECOMMENDED"
        if "MEDIUM" in pr_risk_level:
            return "REVIEW_REQUIRED"
        return "SAFE_TO_MERGE"