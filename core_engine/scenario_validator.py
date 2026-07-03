"""
Scenario Validator — SCORING system, not hard rejection.

Replaces the previous over-strict grounding validator.
- Scores scenarios by their alignment with evidence
- Does NOT hard-reject scenarios with unknown symbols
- Produces confidence adjustments, not binary valid/invalid

Supports both legacy (failure_scenarios) and new (primary_concern + additional_observations) formats.
"""
from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field
import re


@dataclass
class ScenarioScore:
    """Per-scenario confidence score and diagnostics."""
    scenario_index: int
    confidence_adjustment: float = 1.0  # multiplier to apply (0.0 - 1.0)
    evidence_score: float = 0.5  # proportion of supported_by found in IR (0.0 - 1.0)
    production_reachability_score: float = 1.0  # how much of the scenario is production-reachable
    specificity_score: float = 0.5  # how specific vs generic the scenario is
    issues: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)


@dataclass
class ValidationScore:
    """Overall validation score for the failure simulation."""
    scenarios: list[ScenarioScore] = field(default_factory=list)
    overall_confidence_adjustment: float = 1.0
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def should_downrank_verdict(self) -> bool:
        """Determine if verdict should be downranked based on scores."""
        if not self.scenarios:
            return False
        avg_adjustment = sum(s.confidence_adjustment for s in self.scenarios) / len(self.scenarios)
        return avg_adjustment < 0.5

    @property
    def is_essentially_valid(self) -> bool:
        """Check if the simulation is essentially valid (even with minor issues)."""
        if not self.scenarios:
            return True  # No scenarios = no validation needed
        avg_evidence = sum(s.evidence_score for s in self.scenarios) / len(self.scenarios)
        return avg_evidence >= 0.3  # Even 30% evidence match is acceptable


class ScenarioScorer:
    """
    Scores failure scenarios against evidence and IR data.

    Unlike the previous hard-rejection validator, this produces:
    - confidence_adjustment: multiplier to apply to scenario confidence
    - evidence_score: how well-supported the scenario is
    - warnings: diagnostic notes, not errors
    """
    
    def __init__(self, compressed_ir: dict[str, Any]):
        self.compressed_ir = compressed_ir
        self._build_lookups()
    
    def _build_lookups(self):
        """Build fast lookup sets from Factor IR v3."""
        if "change_graph" in self.compressed_ir:
            self._build_v3_lookups()
        else:
            self._build_legacy_lookups()

    def _build_v3_lookups(self):
        core_context = self.compressed_ir.get("core_context", {}) or {}
        change_graph = self.compressed_ir.get("change_graph", []) or []
        behavior_diff = self.compressed_ir.get("behavior_diff", []) or []
        risk_events = self.compressed_ir.get("risk_events", []) or []

        self.changed_symbols = set()
        self.changed_functions = set()
        self.evidence_files = set()
        
        for node in change_graph:
            if not isinstance(node, dict):
                continue
            symbol = str(node.get("symbol", "")).strip()
            file_path = str(node.get("file", "")).strip()
            if symbol:
                self.changed_functions.add(symbol)
                self.changed_symbols.add(f"{file_path}:{symbol}" if file_path else symbol)
            if file_path:
                self.evidence_files.add(file_path)

        for diff in behavior_diff:
            if not isinstance(diff, dict):
                continue
            symbol = str(diff.get("symbol", "")).strip()
            if symbol:
                self.changed_functions.add(symbol)
                self.changed_symbols.add(symbol)

        self.evidence_values = set(self.changed_functions) | set(self.changed_symbols)
        self.flows = set(core_context.get("flows", []) or [])
        self.entry_points = set(core_context.get("entry_points", []) or [])
        self.risk_event_types = set()
        for event in risk_events:
            if isinstance(event, dict):
                event_type = event.get("type", "")
                if event_type:
                    self.risk_event_types.add(event_type)

        self.behavior_diff_symbols = {
            str(diff.get("symbol", "")).strip()
            for diff in behavior_diff
            if isinstance(diff, dict) and diff.get("symbol")
        }
        
        self.non_production_symbols = {
            symbol
            for symbol in self.changed_symbols
            if "/test" in symbol.lower() or "test_" in symbol.lower()
        }

    def _build_legacy_lookups(self):
        """Build lookups from legacy multi-view IR."""
        self.changed_symbols = set(self.compressed_ir.get("changed_symbols", []))
        self.changed_functions = set(self.compressed_ir.get("changed_functions", []))
        self.behavior_diff_symbols = set()

        self.evidence_values = set()
        for evidence in self.compressed_ir.get("evidence", []):
            if isinstance(evidence, dict):
                value = evidence.get("value", "")
                if value:
                    self.evidence_values.add(value)

        self.flows = set(self.compressed_ir.get("flows", []))
        self.entry_points = set(self.compressed_ir.get("entry_points", []))
        
        self.risk_event_types = set()
        for event in self.compressed_ir.get("risk_events", []):
            if isinstance(event, dict):
                event_type = event.get("type", "")
                if event_type:
                    self.risk_event_types.add(event_type)

        self.evidence_files = set()
        for evidence in self.compressed_ir.get("evidence", []):
            if isinstance(evidence, dict):
                source = evidence.get("source", "")
                if source:
                    self.evidence_files.add(source)

        self.non_production_symbols = set()
        for evidence in self.compressed_ir.get("evidence", []):
            if isinstance(evidence, dict):
                value = evidence.get("value", "")
                source = evidence.get("source", "")
                if "test" in source.lower() or "test" in value.lower():
                    self.non_production_symbols.add(value)
                    self.non_production_symbols.add(source)
    
    def score(self, failure_simulation: dict[str, Any]) -> ValidationScore:
        """Score failure simulation output (does NOT hard-reject).
        
        Supports both new format (primary_concern, additional_observations) and
        legacy format (failure_scenarios).
        """
        result = ValidationScore()
        
        if not isinstance(failure_simulation, dict):
            result.warnings.append("Failure simulation is not a valid dict")
            result.overall_confidence_adjustment = 0.5
            return result
        
        # New format: primary_concern + additional_observations
        all_items = []
        primary = failure_simulation.get("primary_concern")
        if primary and isinstance(primary, dict):
            score = self._score_primary_concern(primary, 0)
            if score:
                result.scenarios.append(score)
                all_items.append(primary)
        
        observations = failure_simulation.get("additional_observations", [])
        for i, obs in enumerate(observations):
            score = self._score_additional_observation(obs, i + 1)
            if score:
                result.scenarios.append(score)
                all_items.append(obs)
        
        # Legacy format: architectural_observations, highest_production_risks
        if not all_items:
            observations = failure_simulation.get("architectural_observations", [])
            risks = failure_simulation.get("highest_production_risks", [])
            
            for i, obs in enumerate(observations):
                score = self._score_architectural_observation(obs, i)
                if score:
                    result.scenarios.append(score)
                    all_items.append(obs)
            
            for i, risk in enumerate(risks):
                score = self._score_production_risk(risk, i + len(observations))
                if score:
                    result.scenarios.append(score)
                    all_items.append(risk)
        
        # Legacy format: failure_scenarios
        if not all_items:
            scenarios = failure_simulation.get("failure_scenarios", [])
            if scenarios:
                for i, scenario in enumerate(scenarios):
                    score = self._score_legacy_scenario(scenario, i)
                    if score:
                        result.scenarios.append(score)
            else:
                result.notes.append("No scenarios or observations to validate")
                return result

        # Calculate overall confidence adjustment
        if result.scenarios:
            result.overall_confidence_adjustment = sum(
                s.confidence_adjustment for s in result.scenarios
            ) / len(result.scenarios)

        return result
    
    def _score_primary_concern(self, concern: dict[str, Any], index: int) -> ScenarioScore | None:
        """Score a single primary concern (new format)."""
        if not isinstance(concern, dict):
            return None
        
        score = ScenarioScore(scenario_index=index)
        
        # 1. Evidence grounding score from execution_path symbols
        execution_path = concern.get("execution_path", "")
        # Extract symbols from execution path (e.g. "A → B → C")
        path_symbols = re.findall(r'[a-zA-Z_][a-zA-Z0-9_.]*', execution_path)
        if path_symbols:
            found_count = sum(1 for sym in path_symbols if self._symbol_exists_in_ir(sym))
            score.evidence_score = found_count / len(path_symbols)
            
            if found_count < len(path_symbols):
                missing = [sym for sym in path_symbols if not self._symbol_exists_in_ir(sym)]
                score.issues.append(f"Symbol(s) not found in IR: {', '.join(missing[:3])}")
            if found_count > 0:
                score.strengths.append(f"{found_count}/{len(path_symbols)} execution path symbols found in IR")
        else:
            score.evidence_score = 0.5
            score.issues.append("No execution path symbols to validate")
        
        # 2. Production reachability
        why_blocking = concern.get("why_blocking", "")
        if len(why_blocking) > 100:
            score.production_reachability_score = 0.9
        elif len(why_blocking) > 50:
            score.production_reachability_score = 0.7
        else:
            score.production_reachability_score = 0.5
        
        # 3. Specificity from title and required_validation
        title = concern.get("title", "")
        required_validation = concern.get("required_validation", "")
        total_length = len(title) + len(required_validation)
        if total_length > 100:
            score.specificity_score = 0.8
        elif total_length > 50:
            score.specificity_score = 0.6
        else:
            score.specificity_score = 0.4
        
        # Calculate overall confidence adjustment
        score.confidence_adjustment = (
            score.evidence_score * 0.4 +
            score.production_reachability_score * 0.3 +
            score.specificity_score * 0.3
        )
        score.confidence_adjustment = max(0.1, score.confidence_adjustment)
        
        return score
    
    def _score_additional_observation(self, obs: dict[str, Any], index: int) -> ScenarioScore | None:
        """Score a single additional observation (new format)."""
        if not isinstance(obs, dict):
            return None
        
        score = ScenarioScore(scenario_index=index)
        
        # 1. Evidence grounding score from symbols
        symbols = obs.get("symbols", [])
        if symbols:
            found_count = sum(1 for sym in symbols if self._symbol_exists_in_ir(sym))
            score.evidence_score = found_count / len(symbols)
            
            if found_count < len(symbols):
                missing = [sym for sym in symbols if not self._symbol_exists_in_ir(sym)]
                score.issues.append(f"Symbol(s) not found in IR: {', '.join(missing[:3])}")
            if found_count > 0:
                score.strengths.append(f"{found_count}/{len(symbols)} symbols found in IR")
        else:
            score.evidence_score = 0.3
            score.issues.append("No symbols cited — weak grounding")
        
        # 2. Production reachability
        score.production_reachability_score = 0.7
        
        # 3. Specificity from observation text
        observation = obs.get("observation", "")
        if len(observation) > 200:
            score.specificity_score = 0.8
        elif len(observation) > 100:
            score.specificity_score = 0.6
        else:
            score.specificity_score = 0.4
        
        # Calculate overall confidence adjustment
        score.confidence_adjustment = (
            score.evidence_score * 0.4 +
            score.production_reachability_score * 0.3 +
            score.specificity_score * 0.3
        )
        score.confidence_adjustment = max(0.1, score.confidence_adjustment)
        
        return score
    
    def _score_architectural_observation(self, obs: dict[str, Any], index: int) -> ScenarioScore | None:
        """Score a single architectural observation (legacy format)."""
        if not isinstance(obs, dict):
            return None
        
        score = ScenarioScore(scenario_index=index)
        
        # 1. Evidence grounding score from symbols
        symbols = obs.get("symbols", [])
        if symbols:
            found_count = sum(1 for sym in symbols if self._symbol_exists_in_ir(sym))
            score.evidence_score = found_count / len(symbols)
            
            if found_count < len(symbols):
                missing = [sym for sym in symbols if not self._symbol_exists_in_ir(sym)]
                score.issues.append(f"Symbol(s) not found in IR: {', '.join(missing[:3])}")
            if found_count > 0:
                score.strengths.append(f"{found_count}/{len(symbols)} symbols found in IR")
        else:
            score.evidence_score = 0.3
            score.issues.append("No symbols cited — weak grounding")
        
        # 2. Production reachability from evidence_strength
        evidence_strength = obs.get("evidence_strength", "Limited")
        if evidence_strength == "Strong":
            score.production_reachability_score = 0.9
        elif evidence_strength == "Moderate":
            score.production_reachability_score = 0.6
        else:
            score.production_reachability_score = 0.3
        
        # 3. Specificity from observation text
        observation = obs.get("observation", "")
        if len(observation) > 200:
            score.specificity_score = 0.8
        elif len(observation) > 100:
            score.specificity_score = 0.6
        else:
            score.specificity_score = 0.4
        
        # Calculate overall confidence adjustment
        score.confidence_adjustment = (
            score.evidence_score * 0.4 +
            score.production_reachability_score * 0.3 +
            score.specificity_score * 0.3
        )
        score.confidence_adjustment = max(0.1, score.confidence_adjustment)
        
        return score
    
    def _score_production_risk(self, risk: dict[str, Any], index: int) -> ScenarioScore | None:
        """Score a single production risk (legacy format)."""
        if not isinstance(risk, dict):
            return None
        
        score = ScenarioScore(scenario_index=index)
        
        # 1. Evidence grounding score from affected_symbols
        symbols = risk.get("affected_symbols", [])
        if symbols:
            found_count = sum(1 for sym in symbols if self._symbol_exists_in_ir(sym))
            score.evidence_score = found_count / len(symbols)
            
            if found_count < len(symbols):
                missing = [sym for sym in symbols if not self._symbol_exists_in_ir(sym)]
                score.issues.append(f"Symbol(s) not found in IR: {', '.join(missing[:3])}")
            if found_count > 0:
                score.strengths.append(f"{found_count}/{len(symbols)} symbols found in IR")
        else:
            score.evidence_score = 0.3
            score.issues.append("No affected_symbols cited — weak grounding")
        
        # 2. Production reachability
        score.production_reachability_score = 0.8  # Production risks are inherently production-reachable
        
        # 3. Specificity from description and suggested_validation
        description = risk.get("description", "")
        suggested_validation = risk.get("suggested_validation", "")
        total_length = len(description) + len(suggested_validation)
        if total_length > 200:
            score.specificity_score = 0.8
        elif total_length > 100:
            score.specificity_score = 0.6
        else:
            score.specificity_score = 0.4
        
        # Calculate overall confidence adjustment
        score.confidence_adjustment = (
            score.evidence_score * 0.5 +
            score.production_reachability_score * 0.25 +
            score.specificity_score * 0.25
        )
        score.confidence_adjustment = max(0.1, score.confidence_adjustment)
        
        return score
    
    def _score_legacy_scenario(self, scenario: dict[str, Any], index: int) -> ScenarioScore:
        """Score a single legacy scenario (old format)."""
        score = ScenarioScore(scenario_index=index)
        
        # 1. Evidence grounding score
        supported_by = scenario.get("supported_by", [])
        if supported_by:
            found_count = sum(1 for sym in supported_by if self._symbol_exists_in_ir(sym))
            score.evidence_score = found_count / len(supported_by)
            
            if found_count < len(supported_by):
                missing = [sym for sym in supported_by if not self._symbol_exists_in_ir(sym)]
                score.issues.append(f"Symbol(s) not found in IR: {', '.join(missing[:3])}")
            if found_count > 0:
                score.strengths.append(f"{found_count}/{len(supported_by)} supported_by symbols found in IR")
        else:
            score.evidence_score = 0.3  # No evidence cited; weak but not invalid
            score.issues.append("No supported_by evidence cited — weak grounding")
        
        # 2. Production reachability score
        merge_risk_level = scenario.get("merge_risk_level", "MEDIUM")
        
        if merge_risk_level in ("HIGH", "CRITICAL"):
            # For high-risk scenarios, check production reachability
            combined_entities = list(supported_by)
            if combined_entities:
                reachable_count = sum(1 for e in combined_entities if self._is_production_reachable(e))
                score.production_reachability_score = reachable_count / len(combined_entities)
                
                if reachable_count < len(combined_entities):
                    score.issues.append("Some entities may not be production-reachable")
                if reachable_count > 0:
                    score.strengths.append("Scenario has production-reachable entities")
            else:
                score.production_reachability_score = 0.5  # Uncertain — neither confirmed nor denied
                score.issues.append("Cannot verify production reachability (no entities to check)")
        else:
            # Lower risk scenarios don't require production reachability verification
            score.production_reachability_score = 1.0
        
        # 3. Specificity score (penalize generic scenarios)
        title = scenario.get("title", "")
        if len(title) < 15:
            score.specificity_score = 0.3
            score.issues.append("Scenario title is too generic (< 15 chars)")
        elif len(title) < 30:
            score.specificity_score = 0.6
            score.notes.append("Scenario title is somewhat generic")
        else:
            score.specificity_score = 1.0
            score.strengths.append("Scenario title is specific and descriptive")
        
        # 4. Confidence calibration
        confidence = scenario.get("confidence", 0.0)
        if confidence > 0.8 and score.evidence_score < 0.5:
            score.issues.append(f"High confidence ({confidence}) but low evidence grounding ({score.evidence_score:.2f}) — overconfidence")
        if confidence < 0.3 and score.evidence_score > 0.7:
            score.notes.append(f"Low confidence ({confidence}) despite strong evidence ({score.evidence_score:.2f}) — underconfidence")
        
        # 5. Calculate overall confidence adjustment
        # Weight: evidence 50%, production reachability 25%, specificity 25%
        score.confidence_adjustment = (
            score.evidence_score * 0.5 +
            score.production_reachability_score * 0.25 +
            score.specificity_score * 0.25
        )
        
        # Floor at 0.1 — never fully discard a scenario
        score.confidence_adjustment = max(0.1, score.confidence_adjustment)
        
        return score
    
    def _symbol_exists_in_ir(self, symbol: str) -> bool:
        """Check if a symbol exists in any IR evidence."""
        if symbol in self.changed_symbols:
            return True
        if symbol in self.changed_functions:
            return True
        if symbol in self.evidence_values:
            return True
        if symbol in self.evidence_files:
            return True
        for stored in self.changed_symbols:
            if symbol in stored or stored in symbol:
                return True
        return False
    
    def _is_production_reachable(self, symbol: str) -> bool:
        """Check if a symbol is production reachable."""
        if symbol in self.non_production_symbols:
            return False
        symbol_lower = symbol.lower()
        if "/tests/" in symbol_lower or "/test/" in symbol_lower:
            return False
        return True


def score_scenarios(failure_simulation: dict[str, Any], normalized_facts_or_ir: Any) -> ValidationScore:
    """Convenience function for scoring failure scenarios.
    
    Args:
        failure_simulation: Failure simulation output from LLM or deterministic builder.
        normalized_facts_or_ir: Either NormalizedReviewFacts or compressed IR dict.
            If NormalizedReviewFacts, extracts compression stats for scoring.
            If dict, uses directly as compressed IR.
            
    Returns:
        ValidationScore with confidence adjustments and diagnostics.
    """
    # Extract compressed IR from normalized facts if needed
    if hasattr(normalized_facts_or_ir, 'compression_stats'):
        # It's NormalizedReviewFacts - extract compression stats
        compressed_ir = normalized_facts_or_ir.compression_stats
    else:
        # It's already a dict (legacy behavior)
        compressed_ir = normalized_facts_or_ir
    
    scorer = ScenarioScorer(compressed_ir)
    return scorer.score(failure_simulation)
