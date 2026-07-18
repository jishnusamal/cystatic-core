"""Presentation context models and builders.

Separates deterministic compiler facts from LLM narrative generation.
The context owns all metrics. The LLM owns only language.
"""

from presentation.context.comment_context import (
    GithubCommentContext,
    ContextExecutionSection,
    ContextOperationalSection,
    ContextValidationSection,
    ContextSurprisingDiscovery,
)
from presentation.context.builder import PresentationContextBuilder

__all__ = [
    "GithubCommentContext",
    "ContextExecutionSection",
    "ContextOperationalSection",
    "ContextValidationSection",
    "ContextSurprisingDiscovery",
    "PresentationContextBuilder",
]