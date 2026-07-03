"""
Evidence Normalization Layer — transforms deterministic analysis into reviewer-ready facts.

This layer sits between InferencePipeline and ReviewPipeline, converting internal
reasoning artifacts into engineering facts that a Staff Engineer would review.
"""
from __future__ import annotations

__all__ = [
    "EvidenceNormalizer",
    "ReviewPacketBuilder",
]

# Lazy imports to avoid circular dependencies
def __getattr__(name: str):
    if name == "EvidenceNormalizer":
        from core_engine.normalization.normalizer import EvidenceNormalizer
        return EvidenceNormalizer
    if name == "ReviewPacketBuilder":
        from core_engine.normalization.review_packet_builder import ReviewPacketBuilder
        return ReviewPacketBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
