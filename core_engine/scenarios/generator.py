"""
Failure Scenario Generator

Generates downstream failure scenarios from Impact Hypotheses.
Synthesizes concrete failure scenarios that could result from the change.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from core_engine.models.impact_hypothesis import ImpactHypothesis
from core_engine.models.failure_scenario import FailureScenario


class FailureScenarioGenerator:
    """Generate downstream failure scenarios from impact hypotheses.
    
    This generator:
    - Takes probabilistic ImpactHypotheses as input
    - Produces concrete FailureScenarios
    - Synthesizes failure chains from evidence
    - Never claims certainty - always includes confidence
    """
    
    # Failure scenario templates by impact type
    FAILURE_TEMPLATES = {
        "financial_impact": [
            "Double charge or duplicate payment processing",
            "Incorrect tax calculation leading to compliance issues",
            "Payment amount mismatch between systems",
            "Refund processing failure",
            "Invoice amount discrepancy",
        ],
        "security_impact": [
            "Authentication bypass allowing unauthorized access",
            "Permission escalation exposing sensitive data",
            "Session hijacking due to token validation failure",
            "Credential exposure through logging or error messages",
        ],
        "transaction_impact": [
            "Partial transaction commit leaving system in inconsistent state",
            "Transaction rollback failure causing data corruption",
            "Race condition in concurrent transaction processing",
            "Deadlock in distributed transaction coordination",
        ],
        "reliability_impact": [
            "Retry storm causing cascading failures",
            "Duplicate processing due to failed idempotency check",
            "Circuit breaker not triggering on persistent failures",
            "Infinite retry loop exhausting resources",
        ],
        "consistency_impact": [
            "Stale cache serving outdated data",
            "Cache invalidation miss causing data inconsistency",
            "Race condition between cache update and database write",
            "Cache stampede on popular data expiration",
        ],
        "dependency_impact": [
            "External service timeout causing cascading failure",
            "API contract mismatch leading to data corruption",
            "Rate limiting exceeded causing service degradation",
            "External dependency failure with no fallback",
        ],
        "state_impact": [
            "State corruption due to concurrent modification",
            "State machine transition violation",
            "Inconsistent state across distributed nodes",
            "State loss during restart or crash",
        ],
        "data_coupling": [
            "Data corruption due to shared table modification",
            "Schema change breaking dependent queries",
            "Constraint violation from concurrent writes",
            "Data migration failure leaving partial updates",
        ],
        "event_coupling": [
            "Event loss due to consumer failure",
            "Duplicate event processing causing side effects",
            "Event ordering violation breaking assumptions",
            "Dead letter queue buildup indicating processing failure",
        ],
        "domain_coupling": [
            "Cross-domain data inconsistency",
            "Domain boundary violation causing business logic errors",
            "Saga compensation failure in distributed transaction",
            "Domain event not triggering expected reactions",
        ],
    }
    
    # Silent failure indicators
    SILENT_FAILURE_INDICATORS = [
        "no error raised",
        "silently ignored",
        "logged but not alerted",
        "caught and swallowed",
        "default value returned",
        "empty result without warning",
        "partial update without notification",
    ]
    
    def generate(self, hypotheses: list[ImpactHypothesis]) -> list[FailureScenario]:
        """Generate failure scenarios from impact hypotheses.
        
        Args:
            hypotheses: List of probabilistic impact hypotheses.
            
        Returns:
            List of concrete failure scenarios.
        """
        scenarios = []
        
        for hypothesis in hypotheses:
            scenario = self._hypothesis_to_scenario(hypothesis)
            if scenario:
                scenarios.append(scenario)
        
        # Deduplicate and rank scenarios
        scenarios = self._dedupe(scenarios)
        scenarios = self._rank_by_severity(scenarios)
        
        return scenarios
    
    def _hypothesis_to_scenario(self, hypothesis: ImpactHypothesis) -> FailureScenario | None:
        """Convert an impact hypothesis to a failure scenario."""
        impact_type = hypothesis.impact_type
        
        # Get failure templates for this impact type
        templates = self.FAILURE_TEMPLATES.get(impact_type, ["Unexpected system behavior"])
        
        # Select the most relevant template based on confidence
        template_index = min(int(hypothesis.confidence * len(templates)), len(templates) - 1)
        failure_title = templates[template_index]
        
        # Generate narrative
        narrative = self._generate_narrative(hypothesis)
        
        # Generate operational impact
        operational_impact = self._generate_operational_impact(hypothesis)
        
        # Generate failure scenario
        scenario = FailureScenario(
            title=failure_title,
            narrative=narrative,
            confidence=hypothesis.confidence,
            impact_type=impact_type,
            source_symbol=hypothesis.source_symbol,
            target_symbol=hypothesis.target_symbol,
            description=hypothesis.description,
            reasoning=self._generate_reasoning(hypothesis),
            affected_business_objects=hypothesis.affected_business_objects,
            affected_domains=hypothesis.affected_domains,
            operational_impact=operational_impact,
            silent_failure=self._is_silent_failure(hypothesis),
            first_observable_signal=self._determine_first_signal(hypothesis),
            merge_risk_level=self._determine_risk_level(hypothesis),
            ci_would_catch=self._would_ci_catch(hypothesis),
            causal_chain=self._build_causal_chain(hypothesis),
            failure_class=self._classify_failure(hypothesis),
        )
        
        return scenario
    
    def _generate_reasoning(self, hypothesis: ImpactHypothesis) -> str:
        """Generate reasoning for the failure scenario."""
        reasoning_parts = [
            f"Impact hypothesis: {hypothesis.description}",
            f"Evidence: {hypothesis.evidence_summary}",
            f"Confidence: {hypothesis.confidence:.2f}",
        ]
        
        if hypothesis.affected_business_objects:
            reasoning_parts.append(f"Business objects: {', '.join(hypothesis.affected_business_objects)}")
        
        if hypothesis.affected_domains:
            reasoning_parts.append(f"Domains: {', '.join(hypothesis.affected_domains)}")
        
        return "\n".join(reasoning_parts)
    
    def _is_silent_failure(self, hypothesis: ImpactHypothesis) -> bool:
        """Determine if this is likely a silent failure."""
        # High-confidence hypotheses with data/state impacts are more likely to be silent
        if hypothesis.confidence >= 0.7 and hypothesis.impact_type in [
            "data_impact", "state_impact", "consistency_impact"
        ]:
            return True
        
        # Check if evidence suggests silent failure
        evidence = hypothesis.evidence_summary.lower()
        return any(indicator in evidence for indicator in self.SILENT_FAILURE_INDICATORS)
    
    def _determine_first_signal(self, hypothesis: ImpactHypothesis) -> str:
        """Determine the first observable signal of this failure."""
        signal_map = {
            "financial_impact": "Payment discrepancy in ledger",
            "security_impact": "Unauthorized access in audit logs",
            "transaction_impact": "Database constraint violation",
            "reliability_impact": "Increased error rate in metrics",
            "consistency_impact": "Data mismatch between cache and database",
            "dependency_impact": "External API timeout or error response",
            "state_impact": "Invalid state transition in state machine",
            "data_coupling": "Data integrity constraint violation",
            "event_coupling": "Message in dead letter queue",
            "domain_coupling": "Business rule violation in domain logic",
        }
        return signal_map.get(hypothesis.impact_type, "Unexpected behavior in logs")
    
    def _determine_risk_level(self, hypothesis: ImpactHypothesis) -> str:
        """Determine the merge risk level for this scenario."""
        if hypothesis.confidence >= 0.8:
            return "HIGH"
        elif hypothesis.confidence >= 0.6:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _would_ci_catch(self, hypothesis: ImpactHypothesis) -> bool:
        """Determine if CI would likely catch this failure."""
        # High-confidence scenarios are more likely to be caught
        if hypothesis.confidence >= 0.8:
            return True
        
        # Certain impact types are more likely to be caught by CI
        catchable_types = {
            "transaction_impact", "reliability_impact", "security_impact"
        }
        
        return hypothesis.impact_type in catchable_types
    
    def _build_causal_chain(self, hypothesis: ImpactHypothesis) -> str:
        """Build a causal chain description."""
        chain_parts = [
            f"1. Change in {hypothesis.source_symbol}",
            f"2. Propagates via {hypothesis.impact_type}",
            f"3. Affects {hypothesis.target_symbol}",
        ]
        
        if hypothesis.affected_business_objects:
            chain_parts.append(f"4. Impacts business objects: {', '.join(hypothesis.affected_business_objects)}")
            chain_parts.append(f"5. Results in: {hypothesis.description}")
        else:
            chain_parts.append(f"4. Results in: {hypothesis.description}")
        
        return " → ".join(chain_parts)
    
    def _classify_failure(self, hypothesis: ImpactHypothesis) -> str:
        """Classify the type of failure."""
        classification_map = {
            "financial_impact": "Financial Error",
            "security_impact": "Security Breach",
            "transaction_impact": "Transaction Failure",
            "reliability_impact": "Reliability Issue",
            "consistency_impact": "Data Inconsistency",
            "dependency_impact": "External Dependency Failure",
            "state_impact": "State Corruption",
            "data_coupling": "Data Integrity Issue",
            "event_coupling": "Event Processing Failure",
            "domain_coupling": "Business Logic Error",
        }
        return classification_map.get(hypothesis.impact_type, "Unknown Failure")
    
    def _generate_narrative(self, hypothesis: ImpactHypothesis) -> str:
        """Generate a narrative for the failure scenario."""
        return f"{hypothesis.description}. {hypothesis.evidence_summary}"
    
    def _generate_operational_impact(self, hypothesis: ImpactHypothesis) -> str:
        """Generate operational impact description."""
        impact_map = {
            "financial_impact": "Potential financial loss and customer billing issues",
            "security_impact": "Security breach risk and unauthorized access potential",
            "transaction_impact": "Data consistency issues and potential transaction failures",
            "reliability_impact": "System reliability degradation and potential outages",
            "consistency_impact": "Data inconsistency between systems and caches",
            "dependency_impact": "External service failures affecting core functionality",
            "state_impact": "System state corruption and unpredictable behavior",
            "data_coupling": "Data integrity issues across shared resources",
            "event_coupling": "Event processing failures and message loss",
            "domain_coupling": "Business logic errors and domain boundary violations",
        }
        return impact_map.get(hypothesis.impact_type, "Potential system instability and user impact")
    
    def _dedupe(self, scenarios: list[FailureScenario]) -> list[FailureScenario]:
        """Deduplicate scenarios."""
        seen = set()
        unique = []
        
        for scenario in scenarios:
            key = (scenario.title, scenario.source_symbol, scenario.target_symbol)
            if key not in seen:
                seen.add(key)
                unique.append(scenario)
        
        return unique
    
    def _rank_by_severity(self, scenarios: list[FailureScenario]) -> list[FailureScenario]:
        """Rank scenarios by severity (highest confidence first)."""
        return sorted(scenarios, key=lambda s: s.confidence, reverse=True)