"""
Confidence Scoring for Impact Hypotheses

Provides confidence adjustment and calibration for hypotheses.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ConfidenceScorer:
    """Score and calibrate confidence for impact hypotheses.
    
    This scorer:
    - Adjusts base confidence from evidence
    - Considers risk anchors
    - Considers evidence quality
    - Never creates new evidence
    - Only adjusts existing confidence scores
    """
    
    # Evidence quality weights
    EVIDENCE_QUALITY_WEIGHTS = {
        "shared_database_table": 1.0,
        "event_publication_consumption": 0.95,
        "endpoint_implementation": 0.9,
        "shared_event_publication": 0.85,
        "shared_event_consumption": 0.85,
        "domain_relationship": 0.8,
        "shared_domain": 0.7,
        "ownership_relationship": 0.6,
        "imports_symbol": 0.5,
        "imports_module": 0.4,
        "naming_similarity": 0.3,
    }
    
    # Risk anchor confidence boosts
    RISK_BOOST = {
        "money_flow": 0.15,
        "authentication": 0.12,
        "authorization": 0.12,
        "transaction_boundary": 0.10,
        "retry_sensitive": 0.08,
        "cache_consistency": 0.05,
        "external_dependency": 0.08,
        "state_mutation": 0.10,
        "idempotency": 0.08,
    }
    
    def score(
        self,
        base_confidence: float,
        evidence_type: str,
        risk_anchors: list[dict[str, Any]],
        evidence_quality: float = 1.0,
    ) -> float:
        """Calculate adjusted confidence score.
        
        Args:
            base_confidence: Base confidence from evidence (0.0-1.0).
            evidence_type: Type of evidence.
            risk_anchors: List of risk anchors present.
            evidence_quality: Quality multiplier for evidence (0.0-1.0).
            
        Returns:
            Adjusted confidence score (0.0-1.0).
        """
        # Start with base confidence
        confidence = base_confidence
        
        # Apply evidence quality weight
        quality_weight = self.EVIDENCE_QUALITY_WEIGHTS.get(evidence_type, 0.5)
        confidence *= quality_weight
        
        # Apply evidence quality multiplier
        confidence *= evidence_quality
        
        # Apply risk anchor boosts
        if risk_anchors:
            max_boost = 0.0
            for anchor in risk_anchors:
                anchor_type = anchor.get("anchor_type", "")
                boost = self.RISK_BOOST.get(anchor_type, 0.0)
                max_boost = max(max_boost, boost)
            
            confidence += max_boost
        
        # Clamp to valid range
        confidence = max(0.0, min(0.95, confidence))
        
        return round(confidence, 3)
    
    def calibrate(self, hypotheses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Calibrate a list of hypotheses.
        
        Args:
            hypotheses: List of hypothesis dicts with confidence scores.
            
        Returns:
            List of calibrated hypothesis dicts.
        """
        calibrated = []
        
        for hypothesis in hypotheses:
            calibrated_hypothesis = dict(hypothesis)
            
            # Recalibrate confidence
            base_confidence = hypothesis.get("confidence", 0.5)
            evidence_type = hypothesis.get("impact_type", "unknown_coupling")
            risk_anchors = hypothesis.get("risk_anchors", [])
            
            calibrated_confidence = self.score(
                base_confidence=base_confidence,
                evidence_type=evidence_type,
                risk_anchors=risk_anchors,
            )
            
            calibrated_hypothesis["confidence"] = calibrated_confidence
            calibrated.append(calibrated_hypothesis)
        
        return calibrated
    
    def get_confidence_tier(self, confidence: float) -> str:
        """Get confidence tier label.
        
        Args:
            confidence: Confidence score (0.0-1.0).
            
        Returns:
            Confidence tier label.
        """
        if confidence >= 0.8:
            return "HIGH"
        elif confidence >= 0.6:
            return "MEDIUM"
        elif confidence >= 0.4:
            return "LOW"
        else:
            return "VERY_LOW"