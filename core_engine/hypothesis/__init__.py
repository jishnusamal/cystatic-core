"""
Hypothesis Package

Generates probabilistic impact hypotheses from Evidence Bundle.
"""
from .generator import HypothesisGenerator
from .confidence import ConfidenceScorer

__all__ = [
    "HypothesisGenerator",
    "ConfidenceScorer",
]