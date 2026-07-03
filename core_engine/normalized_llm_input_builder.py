"""
Normalized LLM Input Builder — builds reviewer-ready input from NormalizedReviewFacts.

This module replaces llm_input_builder for the ReviewPipeline, constructing
LLM input from normalized facts instead of internal artifacts.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.normalized_facts import NormalizedReviewFacts


def build_normalized_llm_input(
    normalized_facts: NormalizedReviewFacts,
    repo: str = "",
    pr_number: int = 0,
) -> dict[str, Any]:
    """Build LLM input from normalized review facts.
    
    This is the ONLY function that constructs data for the LLM from
    normalized facts. The LLM receives only reviewer-ready facts.
    
    Args:
        normalized_facts: NormalizedReviewFacts from EvidenceNormalizationPipeline.
        repo: Repository name.
        pr_number: PR number.
        
    Returns:
        A dict containing only reviewer-ready facts for the LLM.
    """
    llm_input: dict[str, Any] = {
        "repository": {
            "name": repo,
            "language": "Python",  # Placeholder - would come from source adapter
            "framework": "FastAPI",  # Placeholder - would come from source adapter
        },
        "pull_request": {
            "number": pr_number,
            "title": "",
            "description": "",
            "analysis_mode": "FULL_FILE",
        },
    }
    
    # ── Architectural facts ───────────────────────────────────────────────
    llm_input["architectural_facts"] = [
        {
            "title": fact.title,
            "description": fact.description,
            "symbols": fact.symbols,
            "domains": fact.domains,
            "confidence": fact.confidence,
        }
        for fact in normalized_facts.architectural_facts
    ]
    
    # ── Production risks ──────────────────────────────────────────────────
    llm_input["production_risks"] = [
        {
            "title": risk.title,
            "affected_symbols": risk.affected_symbols,
            "affected_domains": risk.affected_domains,
            "production_invariant": risk.production_invariant,
            "confidence": risk.confidence,
            "supporting_evidence": risk.supporting_evidence,
        }
        for risk in normalized_facts.canonical_risks
    ]
    
    # ── Production invariants ─────────────────────────────────────────────
    llm_input["production_invariants"] = [
        {
            "statement": invariant.statement,
            "business_objects": invariant.business_objects,
            "symbols": invariant.symbols,
            "domains": invariant.domains,
            "confidence": invariant.confidence,
        }
        for invariant in normalized_facts.production_invariants
    ]
    
    # ── Validation gaps ───────────────────────────────────────────────────
    llm_input["validation_gaps"] = [
        {
            "description": gap.description,
            "invariant": gap.invariant,
            "existing_validation": gap.existing_validation,
            "missing_validation": gap.missing_validation,
            "affected_symbols": gap.affected_symbols,
            "affected_domains": gap.affected_domains,
            "confidence": gap.confidence,
        }
        for gap in normalized_facts.validation_gaps
    ]
    
    # ── Reviewer questions ────────────────────────────────────────────────
    llm_input["reviewer_questions"] = [
        {
            "question": question.question,
            "context": question.context,
            "related_symbols": question.related_symbols,
            "related_domains": question.related_domains,
            "priority": question.priority,
        }
        for question in normalized_facts.reviewer_questions
    ]
    
    # ── Merge facts ───────────────────────────────────────────────────────
    llm_input["merge_facts"] = [
        {
            "fact": merge_fact.fact,
            "category": merge_fact.category,
            "supporting_evidence": merge_fact.supporting_evidence,
            "confidence": merge_fact.confidence,
        }
        for merge_fact in normalized_facts.merge_facts
    ]
    
    # ── Deterministic verdict ─────────────────────────────────────────────
    llm_input["deterministic_verdict"] = {
        "status": normalized_facts.verdict_input.get("status", "APPROVE"),
        "confidence": normalized_facts.overall_confidence,
    }
    
    return llm_input