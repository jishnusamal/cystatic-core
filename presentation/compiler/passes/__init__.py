"""Presentation compiler passes package.

Every pass has:
- Input contract
- Output contract
- Transformation
- Algorithm
- Invariants
- Failure conditions
- Complexity
- What it must never do
"""
from .base import PresentationPassContext, PresentationCompilationPass
from .normalization import NormalizationPass
from .discovery_extraction import DiscoveryExtractionPass
from .significance_evaluation import SignificanceEvaluationPass
from .ranking import RankingPass
from .surprise_detection import SurpriseDetectionPass
from .compression import CompressionPass
from .narrative_construction import NarrativeConstructionPass
from .visual_composition import VisualCompositionPass
from .ir_assembly import IRAssemblyPass

__all__ = [
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