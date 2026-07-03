"""
Reviewer Question Builder — generates questions from missing evidence.

This module creates reviewer questions directly from missing evidence
and validation gaps, using template-driven patterns.
"""
from __future__ import annotations

from typing import Any

from core_engine.models.normalized_facts import ReviewerQuestion, ValidationGap
from core_engine.models.evidence_bundle import EvidenceBundle


class ReviewerQuestionBuilder:
    """Generates reviewer questions from missing evidence.
    
    Questions are derived from missing runtime paths, ownership gaps,
    rollback concerns, and other missing evidence.
    """
    
    @staticmethod
    def build(
        bundle: EvidenceBundle,
        validation_gaps: list[ValidationGap],
        scenarios: list[dict[str, Any]],
    ) -> list[ReviewerQuestion]:
        """Build reviewer questions from evidence gaps and scenarios.
        
        Args:
            bundle: EvidenceBundle from EvidencePipeline.
            validation_gaps: Identified validation gaps.
            scenarios: Failure scenarios from inference.
            
        Returns:
            List of ReviewerQuestion objects.
        """
        questions: list[ReviewerQuestion] = []
        
        # Generate questions from validation gaps
        questions.extend(ReviewerQuestionBuilder._questions_from_validation_gaps(validation_gaps))
        
        # Generate questions from missing runtime paths
        questions.extend(ReviewerQuestionBuilder._questions_from_runtime_paths(bundle, scenarios))
        
        # Generate questions from missing ownership
        questions.extend(ReviewerQuestionBuilder._questions_from_ownership(bundle))
        
        # Generate questions from rollback concerns
        questions.extend(ReviewerQuestionBuilder._questions_from_rollback(bundle))
        
        # Deduplicate and limit
        questions = ReviewerQuestionBuilder._deduplicate_questions(questions)
        
        return questions[:8]  # Limit to top 8 questions
    
    @staticmethod
    def _questions_from_validation_gaps(
        validation_gaps: list[ValidationGap],
    ) -> list[ReviewerQuestion]:
        """Generate questions from validation gaps."""
        questions: list[ReviewerQuestion] = []
        
        for gap in validation_gaps[:4]:  # Limit to top 4
            try:
                # Generate question based on missing validation
                if "integration test" in gap.missing_validation.lower():
                    question = f"Can we verify the {', '.join(gap.affected_symbols[:2])} execution path through an integration test?"
                    context = f"Missing validation: {gap.missing_validation}"
                    priority = "high"
                elif "end-to-end" in gap.missing_validation.lower():
                    question = f"Has the {', '.join(gap.affected_symbols[:2])} workflow been tested end-to-end?"
                    context = f"Missing validation: {gap.missing_validation}"
                    priority = "high"
                else:
                    question = f"What validation exists for {', '.join(gap.affected_symbols[:2])}?"
                    context = gap.description
                    priority = "medium"
                
                questions.append(ReviewerQuestion(
                    question=question,
                    context=context,
                    related_symbols=gap.affected_symbols[:3],
                    related_domains=gap.affected_domains[:2],
                    priority=priority,
                ))
            except Exception:
                continue
        
        return questions
    
    @staticmethod
    def _questions_from_runtime_paths(
        bundle: EvidenceBundle,
        scenarios: list[dict[str, Any]],
    ) -> list[ReviewerQuestion]:
        """Generate questions from missing runtime paths."""
        questions: list[ReviewerQuestion] = []
        
        # Check for scenarios with missing runtime paths
        for scenario in scenarios[:3]:  # Limit to top 3
            try:
                causal_chain = scenario.get("causal_chain", "")
                if not causal_chain:
                    continue
                
                # Check if runtime path is verified
                ci_would_catch = scenario.get("ci_would_catch", False)
                
                if not ci_would_catch:
                    symbols = scenario.get("supported_by", [])
                    question = f"Has the {causal_chain[:80]} path been verified under production-like load?"
                    
                    questions.append(ReviewerQuestion(
                        question=question,
                        context=f"Scenario: {scenario.get('title', 'Unknown')}",
                        related_symbols=symbols[:3],
                        related_domains=[],
                        priority="high",
                    ))
            except Exception:
                continue
        
        # Check for cross-domain evidence without runtime verification
        cross_domain = [
            ev for ev in bundle.impact_evidence
            if ev.evidence_type and "cross" in ev.evidence_type.lower()
        ]
        
        for ev in cross_domain[:2]:  # Limit to top 2
            try:
                source = ev.source.name if hasattr(ev.source, "name") else ""
                target = ev.target.name if hasattr(ev.target, "name") else ""
                
                if source and target:
                    question = f"Can we verify the {source} → {target} cross-domain call path in integration tests?"
                    
                    questions.append(ReviewerQuestion(
                        question=question,
                        context="Cross-domain execution path requires runtime verification",
                        related_symbols=[source, target],
                        related_domains=[],
                        priority="high",
                    ))
            except Exception:
                continue
        
        return questions
    
    @staticmethod
    def _questions_from_ownership(bundle: EvidenceBundle) -> list[ReviewerQuestion]:
        """Generate questions from missing ownership information."""
        questions: list[ReviewerQuestion] = []
        
        # Check for symbols without clear ownership
        for symbol in bundle.changed_symbols[:3]:  # Limit to top 3
            try:
                symbol_name = symbol.symbol if hasattr(symbol, "symbol") else str(symbol)
                
                # Check if there's ownership information
                has_ownership = any(
                    hasattr(ra, "symbol") and ra.symbol == symbol_name
                    for ra in bundle.risk_anchors
                )
                
                if not has_ownership:
                    question = f"Which component owns the {symbol_name} state transition?"
                    context = f"No ownership information found for {symbol_name}"
                    
                    questions.append(ReviewerQuestion(
                        question=question,
                        context=context,
                        related_symbols=[symbol_name],
                        related_domains=bundle.domains[:2] if bundle.domains else [],
                        priority="medium",
                    ))
            except Exception:
                continue
        
        return questions
    
    @staticmethod
    def _questions_from_rollback(bundle: EvidenceBundle) -> list[ReviewerQuestion]:
        """Generate questions from rollback concerns."""
        questions: list[ReviewerQuestion] = []
        
        # Check for payment/transaction-related symbols
        payment_symbols = [
            cs.symbol for cs in bundle.changed_symbols
            if any(keyword in cs.symbol.lower() for keyword in ["payment", "transaction", "checkout", "invoice"])
        ]
        
        for symbol in payment_symbols[:2]:  # Limit to top 2
            try:
                question = f"What guarantees rollback if {symbol} fails after partial execution?"
                context = f"Payment/transaction operations require rollback guarantees"
                
                questions.append(ReviewerQuestion(
                    question=question,
                    context=context,
                    related_symbols=[symbol],
                    related_domains=bundle.domains[:2] if bundle.domains else [],
                    priority="high",
                ))
            except Exception:
                continue
        
        # Check for external dependencies
        external_effects = [
            se for se in bundle.side_effects
            if hasattr(se, "effect_type") and "external" in se.effect_type.lower()
        ]
        
        for effect in external_effects[:2]:  # Limit to top 2
            try:
                symbol = effect.symbol if hasattr(effect, "symbol") else ""
                if symbol:
                    question = f"What happens if the external call from {symbol} fails or times out?"
                    
                    questions.append(ReviewerQuestion(
                        question=question,
                        context="External dependency requires failure handling",
                        related_symbols=[symbol],
                        related_domains=[],
                        priority="high",
                    ))
            except Exception:
                continue
        
        return questions
    
    @staticmethod
    def _deduplicate_questions(questions: list[ReviewerQuestion]) -> list[ReviewerQuestion]:
        """Remove duplicate questions based on similarity."""
        seen_questions: set[str] = set()
        deduplicated: list[ReviewerQuestion] = []
        
        for question in questions:
            # Normalize question for comparison
            normalized = question.question.lower().strip()
            
            if normalized not in seen_questions:
                seen_questions.add(normalized)
                deduplicated.append(question)
        
        return deduplicated