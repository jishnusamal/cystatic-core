"""Presentation compiler package."""

from .compiler import PresentationCompiler
from .passes import (
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
]