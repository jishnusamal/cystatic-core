"""Presentation Compiler — transforms engineering discovery into a representation optimized for human understanding."""

from .compiler import PresentationCompiler
from .compiler.passes import (
    PresentationPassContext,
    PresentationCompilationPass,
    NormalizationPass,
    DiscoveryExtractionPass,
    SignificanceEvaluationPass,
    RankingPass,
    SurpriseDetectionPass,
    CompressionPass,
    NarrativeConstructionPass,
    VisualCompositionPass,
    IRAssemblyPass,
)
from .model import (
    PresentationIR,
    PresentationDiscovery,
    PresentationEvidence,
    PresentationSummary,
    PresentationMetadata,
    PresentationNarrative,
    PresentationVisual,
    SignificanceMetrics,
    RankingVector,
    SurpriseVector,
    NormalizedDiscovery,
    DiscoveryKind,
    NarrativePosition,
    VisualSemantic,
)
from .llm.context_builder import LLMContextBuilder
from .llm.prompt_builder import PromptBuilder
from .llm.client import LLMClient
from .llm.parser import LLMResponseParser
from .llm.models import (
    LLMContext,
    LLMDiscovery,
    LLMNarrative,
    LLMVisual,
    GithubComment,
    SurprisingDiscovery,
    ExecutionSection,
    OperationalSection,
    ValidationSection,
)
from .llm.validator import CommentValidator
from .renderers.github_comment_renderer import GitHubCommentRenderer
from .publisher.github import GitHubPublisher
from .github_comment_generator import GithubCommentGenerator
from .render.environment import JinjaEnvironment
from .render.github_comment_renderer import GithubCommentRenderer

__all__ = [
    "PresentationCompiler",
    "PresentationPassContext",
    "PresentationCompilationPass",
    "NormalizationPass",
    "DiscoveryExtractionPass",
    "SignificanceEvaluationPass",
    "RankingPass",
    "SurpriseDetectionPass",
    "CompressionPass",
    "NarrativeConstructionPass",
    "VisualCompositionPass",
    "IRAssemblyPass",
    "PresentationIR",
    "PresentationDiscovery",
    "PresentationEvidence",
    "PresentationSummary",
    "PresentationMetadata",
    "PresentationNarrative",
    "PresentationVisual",
    "SignificanceMetrics",
    "RankingVector",
    "SurpriseVector",
    "NormalizedDiscovery",
    "DiscoveryKind",
    "NarrativePosition",
    "VisualSemantic",
    "LLMContextBuilder",
    "PromptBuilder",
    "LLMClient",
    "LLMResponseParser",
    "LLMContext",
    "LLMDiscovery",
    "LLMNarrative",
    "LLMVisual",
    "GithubComment",
    "SurprisingDiscovery",
    "ExecutionSection",
    "OperationalSection",
    "ValidationSection",
    "CommentValidator",
    "GitHubCommentRenderer",
    "GithubCommentRenderer",
    "GithubCommentGenerator",
    "JinjaEnvironment",
    "GitHubPublisher",
]
