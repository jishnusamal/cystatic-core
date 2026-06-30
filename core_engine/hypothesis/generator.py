"""
Impact Hypothesis Generator

Generates probabilistic impact hypotheses from the Evidence Bundle.
This is the first probabilistic layer - everything before is deterministic.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from core_engine.models.evidence_bundle import EvidenceBundle
from core_engine.models.impact_hypothesis import ImpactHypothesis
from core_engine.models.impact_evidence import ImpactEvidence
from core_engine.models.risk_anchor import RiskAnchor
from core_engine.models.side_effect import SideEffect


class HypothesisGenerator:
    """Generate probabilistic impact hypotheses from evidence.
    
    This generator:
    - Takes deterministic EvidenceBundle as input
    - Produces probabilistic ImpactHypotheses
    - Never modifies the evidence bundle
    - Always assigns confidence scores
    """
    
    # Base confidence by evidence type
    EVIDENCE_TYPE_CONFIDENCE = {
        "shared_database_table": 0.8,
        "shared_event_publication": 0.7,
        "shared_event_consumption": 0.7,
        "event_publication_consumption": 0.8,
        "domain_relationship": 0.7,
        "shared_domain": 0.6,
        "ownership_relationship": 0.5,
        "endpoint_implementation": 0.9,
        "naming_similarity": 0.3,
        "imports_module": 0.4,
        "imports_symbol": 0.5,
    }
    
    # Risk multiplier by risk anchor type
    RISK_ANCHOR_MULTIPLIER = {
        "money_flow": 1.5,
        "authentication": 1.4,
        "authorization": 1.4,
        "transaction_boundary": 1.3,
        "retry_sensitive": 1.2,
        "cache_consistency": 1.1,
        "external_dependency": 1.2,
        "state_mutation": 1.3,
        "idempotency": 1.2,
    }
    
    def generate(self, evidence_bundle: EvidenceBundle) -> list[ImpactHypothesis]:
        """Generate impact hypotheses from evidence bundle.
        
        Args:
            evidence_bundle: The deterministic evidence bundle.
            
        Returns:
            List of probabilistic impact hypotheses.
        """
        hypotheses = []
        
        # Generate hypotheses from impact evidence
        for evidence in evidence_bundle.impact_evidence:
            hypothesis = self._evidence_to_hypothesis(evidence, evidence_bundle)
            if hypothesis:
                hypotheses.append(hypothesis)
        
        # Generate hypotheses from risk anchors
        for anchor in evidence_bundle.risk_anchors:
            hypothesis = self._anchor_to_hypothesis(anchor, evidence_bundle)
            if hypothesis:
                hypotheses.append(hypothesis)
        
        # Generate hypotheses from side effects
        for side_effect in evidence_bundle.side_effects:
            hypothesis = self._side_effect_to_hypothesis(side_effect, evidence_bundle)
            if hypothesis:
                hypotheses.append(hypothesis)
        
        # Deduplicate and rank hypotheses
        hypotheses = self._dedupe(hypotheses)
        hypotheses = self._rank_by_confidence(hypotheses)
        
        return hypotheses
    
    def _evidence_to_hypothesis(
        self,
        evidence: dict[str, Any] | ImpactEvidence,
        evidence_bundle: EvidenceBundle,
    ) -> ImpactHypothesis | None:
        """Convert impact evidence to a hypothesis."""
        # Handle both dict and ImpactEvidence object
        if hasattr(evidence, "source"):
            # It's an ImpactEvidence object
            source = evidence.source.id if hasattr(evidence.source, "id") else str(evidence.source)
            target = evidence.target.id if hasattr(evidence.target, "id") else str(evidence.target)
            evidence_type = evidence.evidence_type
            base_confidence = evidence.confidence
            explanation = evidence.explanation
        else:
            # It's a dict
            source = evidence.get("source_symbol", "")
            target = evidence.get("target_symbol", "")
            evidence_type = evidence.get("evidence_type", "")
            base_confidence = evidence.get("confidence", 0.5)
            explanation = evidence.get("explanation", "")
        
        if not source or not target:
            return None
        
        # Adjust confidence based on risk anchors
        confidence = self._adjust_confidence(base_confidence, evidence_bundle)
        
        # Determine impact type
        impact_type = self._determine_impact_type(evidence_type)
        
        # Generate hypothesis description
        description = self._generate_hypothesis_description(
            source, target, evidence_type, explanation
        )
        
        return ImpactHypothesis(
            hypothesis=description,
            source_symbol=source,
            target_symbol=target,
            impact_type=impact_type,
            confidence=confidence,
            description=description,
            evidence_summary=explanation,
            affected_business_objects=self._extract_business_objects(evidence_bundle),
            affected_domains=evidence_bundle.domains,
        )
    
    def _anchor_to_hypothesis(
        self,
        anchor: dict[str, Any] | RiskAnchor,
        evidence_bundle: EvidenceBundle,
    ) -> ImpactHypothesis | None:
        """Convert risk anchor to a hypothesis."""
        # Handle both dict and RiskAnchor object
        if hasattr(anchor, "anchor_type"):
            # It's a RiskAnchor object
            anchor_type = anchor.anchor_type.value if hasattr(anchor.anchor_type, "value") else str(anchor.anchor_type)
            symbol = anchor.symbol
            base_confidence = anchor.confidence
            explanation = anchor.explanation
        else:
            # It's a dict
            anchor_type = anchor.get("anchor_type", "")
            symbol = anchor.get("symbol", "")
            base_confidence = anchor.get("confidence", 0.5)
            explanation = anchor.get("explanation", "")
        
        if not symbol:
            return None
        
        # Risk anchors get a confidence boost
        multiplier = self.RISK_ANCHOR_MULTIPLIER.get(anchor_type, 1.0)
        confidence = min(base_confidence * multiplier, 0.95)
        
        # Determine impact type based on anchor type
        impact_type = self._anchor_type_to_impact_type(anchor_type)
        
        # Generate hypothesis description
        description = f"Risk anchor '{anchor_type}' detected in '{symbol}': {explanation}"
        
        # Get business domain
        if hasattr(anchor, "business_domain"):
            business_domain = anchor.business_domain
        else:
            business_domain = anchor.get("business_domain")
        
        return ImpactHypothesis(
            hypothesis=description,
            source_symbol=symbol,
            target_symbol=symbol,  # Self-impact for risk anchors
            impact_type=impact_type,
            confidence=confidence,
            description=description,
            evidence_summary=explanation,
            affected_business_objects=self._extract_business_objects_from_anchor(anchor),
            affected_domains=[business_domain] if business_domain else evidence_bundle.domains,
        )
    
    def _side_effect_to_hypothesis(
        self,
        side_effect: dict[str, Any] | SideEffect,
        evidence_bundle: EvidenceBundle,
    ) -> ImpactHypothesis | None:
        """Convert side effect to a hypothesis."""
        # Handle both dict and SideEffect object
        if hasattr(side_effect, "symbol"):
            # It's a SideEffect object
            symbol = side_effect.symbol
            effect_type = side_effect.effect_type
            description = side_effect.description
            base_confidence = side_effect.confidence
        else:
            # It's a dict
            symbol = side_effect.get("symbol", "")
            effect_type = side_effect.get("effect_type", "")
            description = side_effect.get("description", "")
            base_confidence = side_effect.get("confidence", 0.5)
        
        if not symbol or not effect_type:
            return None
        
        # Side effects get moderate confidence
        confidence = min(base_confidence * 1.1, 0.85)
        
        # Determine impact type
        impact_type = self._side_effect_type_to_impact_type(effect_type)
        
        return ImpactHypothesis(
            hypothesis=f"Side effect '{effect_type}' detected: {description}",
            source_symbol=symbol,
            target_symbol=symbol,  # Self-impact for side effects
            impact_type=impact_type,
            confidence=confidence,
            description=f"Side effect '{effect_type}' detected: {description}",
            evidence_summary=description,
            affected_business_objects=self._extract_business_objects(evidence_bundle),
            affected_domains=evidence_bundle.domains,
        )
    
    def _adjust_confidence(self, base_confidence: float, evidence_bundle: EvidenceBundle) -> float:
        """Adjust confidence based on risk anchors in the bundle."""
        if not evidence_bundle.risk_anchors:
            return base_confidence
        
        # Boost confidence if risk anchors are present
        risk_multiplier = 1.0
        for anchor in evidence_bundle.risk_anchors:
            # Handle both dict and RiskAnchor object
            if hasattr(anchor, "anchor_type"):
                anchor_type = anchor.anchor_type.value if hasattr(anchor.anchor_type, "value") else str(anchor.anchor_type)
            else:
                anchor_type = anchor.get("anchor_type", "")
            
            multiplier = self.RISK_ANCHOR_MULTIPLIER.get(anchor_type, 1.0)
            risk_multiplier = max(risk_multiplier, multiplier)
        
        adjusted = base_confidence * risk_multiplier
        return min(adjusted, 0.95)
    
    def _determine_impact_type(self, evidence_type: str) -> str:
        """Determine impact type from evidence type."""
        mapping = {
            "shared_database_table": "data_coupling",
            "shared_event_publication": "event_coupling",
            "shared_event_consumption": "event_coupling",
            "event_publication_consumption": "event_coupling",
            "domain_relationship": "domain_coupling",
            "shared_domain": "domain_coupling",
            "ownership_relationship": "ownership_coupling",
            "endpoint_implementation": "api_coupling",
            "naming_similarity": "semantic_coupling",
            "imports_module": "dependency_coupling",
            "imports_symbol": "dependency_coupling",
        }
        return mapping.get(evidence_type, "unknown_coupling")
    
    def _anchor_type_to_impact_type(self, anchor_type: str) -> str:
        """Convert risk anchor type to impact type."""
        mapping = {
            "money_flow": "financial_impact",
            "authentication": "security_impact",
            "authorization": "security_impact",
            "transaction_boundary": "transaction_impact",
            "retry_sensitive": "reliability_impact",
            "cache_consistency": "consistency_impact",
            "external_dependency": "dependency_impact",
            "state_mutation": "state_impact",
            "idempotency": "reliability_impact",
        }
        return mapping.get(anchor_type, "unknown_impact")
    
    def _side_effect_type_to_impact_type(self, effect_type: str) -> str:
        """Convert side effect type to impact type."""
        mapping = {
            "database_write": "data_impact",
            "database_read": "data_impact",
            "cache_operation": "performance_impact",
            "http_call": "external_impact",
            "queue_publish": "async_impact",
            "queue_consume": "async_impact",
            "file_io": "io_impact",
            "external_api": "external_impact",
        }
        return mapping.get(effect_type, "unknown_impact")
    
    def _generate_hypothesis_description(
        self,
        source: str,
        target: str,
        evidence_type: str,
        explanation: str,
    ) -> str:
        """Generate a human-readable hypothesis description."""
        return f"Change to '{source}' may impact '{target}' via {evidence_type}: {explanation}"
    
    def _extract_business_objects(self, evidence_bundle: EvidenceBundle) -> list[str]:
        """Extract business object names from evidence bundle."""
        objects = []
        for bo in evidence_bundle.business_objects:
            # Handle both dict and BusinessObject object
            if hasattr(bo, "name"):
                # It's a BusinessObject object
                name = bo.name
            else:
                # It's a dict
                name = bo.get("name", "")
            
            if name:
                objects.append(name)
        return objects
    
    def _extract_business_objects_from_anchor(self, anchor: dict[str, Any] | RiskAnchor) -> list[str]:
        """Extract business objects from a risk anchor."""
        objects = []
        
        # Handle both dict and RiskAnchor object
        if hasattr(anchor, "business_object"):
            # It's a RiskAnchor object
            business_object = anchor.business_object
        else:
            # It's a dict
            business_object = anchor.get("business_object")
        
        if business_object:
            objects.append(business_object)
        return objects
    
    def _dedupe(self, hypotheses: list[ImpactHypothesis]) -> list[ImpactHypothesis]:
        """Deduplicate hypotheses."""
        seen = set()
        unique = []
        
        for hypothesis in hypotheses:
            key = (hypothesis.source_symbol, hypothesis.target_symbol, hypothesis.impact_type)
            if key not in seen:
                seen.add(key)
                unique.append(hypothesis)
        
        return unique
    
    def _rank_by_confidence(self, hypotheses: list[ImpactHypothesis]) -> list[ImpactHypothesis]:
        """Rank hypotheses by confidence (highest first)."""
        return sorted(hypotheses, key=lambda h: h.confidence, reverse=True)