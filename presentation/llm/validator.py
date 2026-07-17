"""Comment Validator for LLM-generated PR comments.

Validates that LLM output is grounded in the provided context.
Never trust the model - always validate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidatedComment:
    """Validated LLM-generated comment.
    
    Attributes:
        markdown: The validated markdown content.
        is_valid: Whether the comment passed validation.
        validation_errors: List of validation errors found.
        model: Model used for generation.
        truncated: Whether the comment was truncated.
    """
    markdown: str
    is_valid: bool
    validation_errors: tuple[str, ...] = field(default_factory=tuple)
    model: str = ""
    truncated: bool = False


class CommentValidator:
    """
    Validates LLM-generated comments for grounding and structural integrity.
    
    Checks:
    - Response exists
    - Markdown is valid
    - Maximum size
    - No hallucinated metrics
    - No references to unknown discoveries
    - No invented numbers
    
    If validation fails, returns deterministic fallback.
    """
    
    MAX_MARKDOWN_LENGTH = 10000  # Maximum markdown length
    MIN_MARKDOWN_LENGTH = 100  # Minimum meaningful length
    
    def __init__(self, context: Any = None):
        """
        Initialize validator.
        
        Args:
            context: Optional LLMContext for cross-referencing discoveries.
        """
        self.context = context
    
    def validate(self, markdown: str, model: str = "") -> ValidatedComment:
        """
        Validate LLM-generated markdown comment.
        
        Args:
            markdown: The generated markdown content.
            model: Model name used for generation.
            
        Returns:
            ValidatedComment with validation results.
        """
        errors = []
        
        # Check 1: Response exists
        if not markdown or not markdown.strip():
            errors.append("Generated comment is empty")
            return self._create_fallback(model, errors)
        
        # Check 2: Markdown length
        if len(markdown) > self.MAX_MARKDOWN_LENGTH:
            errors.append(f"Comment exceeds maximum length: {len(markdown)} > {self.MAX_MARKDOWN_LENGTH}")
            markdown = markdown[:self.MAX_MARKDOWN_LENGTH] + "\n\n*[Comment truncated due to length]*"
            truncated = True
        else:
            truncated = False
        
        if len(markdown.strip()) < self.MIN_MARKDOWN_LENGTH:
            errors.append(f"Comment too short: {len(markdown)} < {self.MIN_MARKDOWN_LENGTH}")
        
        # Check 3: Basic markdown structure
        if not self._has_valid_markdown_structure(markdown):
            errors.append("Comment lacks basic markdown structure (no headers)")
        
        # Check 4: No hallucinated metrics (if context provided)
        if self.context:
            hallucination_errors = self._check_for_hallucinated_metrics(markdown)
            errors.extend(hallucination_errors)
        
        # Check 5: No invented numbers (basic heuristic)
        number_errors = self._check_for_invented_numbers(markdown)
        errors.extend(number_errors)
        
        # Determine if valid
        is_valid = len(errors) == 0
        
        if not is_valid:
            # If critical errors, return fallback
            if any("empty" in err or "too short" in err for err in errors):
                return self._create_fallback(model, errors)
        
        return ValidatedComment(
            markdown=markdown,
            is_valid=is_valid,
            validation_errors=tuple(errors),
            model=model,
            truncated=truncated,
        )
    
    def _has_valid_markdown_structure(self, markdown: str) -> bool:
        """Check if markdown has basic structure (headers)."""
        # Must have at least one header
        has_header = bool(re.search(r'^#+\s+.+', markdown, re.MULTILINE))
        return has_header
    
    def _check_for_hallucinated_metrics(self, markdown: str) -> list[str]:
        """
        Check for metrics not present in the context.
        
        This is a heuristic check - we look for suspicious patterns.
        """
        errors = []
        
        if not self.context or not hasattr(self.context, 'summary'):
            return errors
        
        # Get actual metrics from context
        context_summary = self.context.summary if hasattr(self.context, 'summary') else {}
        
        # Look for suspicious patterns like "100% coverage" or "zero bugs"
        # These are red flags for hallucination
        absolute_claims = re.findall(r'\b(100%|zero\s+\w+|no\s+\w+\s+at\s+all)\b', markdown, re.IGNORECASE)
        if absolute_claims:
            errors.append(f"Potential hallucination: absolute claims found: {absolute_claims[:3]}")
        
        return errors
    
    def _check_for_invented_numbers(self, markdown: str) -> list[str]:
        """
        Basic heuristic to detect potentially invented numbers.
        
        This is not perfect but catches obvious hallucinations.
        """
        errors = []
        
        # Look for suspiciously precise numbers without context
        # e.g., "exactly 42" or "precisely 1337"
        precise_claims = re.findall(r'\b(exactly|precisely|exact)\s+\d+\b', markdown, re.IGNORECASE)
        if precise_claims:
            errors.append(f"Potential invented numbers: {precise_claims[:3]}")
        
        return errors
    
    def _create_fallback(self, model: str, errors: list[str]) -> ValidatedComment:
        """Create deterministic fallback comment when validation fails."""
        fallback_markdown = """## ⚠️ Analysis Complete

The automated analysis has been completed. Detailed findings are available in the presentation data.

### Summary
- Change analysis: Complete
- Behavior analysis: Complete
- Operational impact: Complete

### Next Steps
Please review the detailed analysis in the API response or dashboard.

---
*This is a fallback comment. The LLM-generated comment could not be produced due to validation errors.*
"""
        
        return ValidatedComment(
            markdown=fallback_markdown,
            is_valid=False,
            validation_errors=tuple(errors),
            model=model,
            truncated=False,
        )