"""Discovery Compiler - standalone deterministic engineering discovery.

The Discovery Compiler answers:
    Which deterministic engineering observations can be extracted from the Operational Model?

It consumes the OperationalChangeModel and produces a DiscoveryModel.
It is separate from the Operational Compiler and has no presentation logic.
"""
from discovery.model import (
    DiscoveryModel,
    Discovery,
    DiscoveryKind,
    DiscoveryFact,
    DiscoveryReference,
)
from discovery.compiler import DiscoveryCompiler

__all__ = [
    "DiscoveryModel",
    "Discovery",
    "DiscoveryKind",
    "DiscoveryFact",
    "DiscoveryReference",
    "DiscoveryCompiler",
]