"""Discovery Compiler - standalone deterministic engineering discovery.

The Discovery Compiler answers:
    Which deterministic engineering observations can be extracted from the Operational Model?

It consumes the OperationalChangeModel and produces a DiscoveryModel.
It is separate from the Operational Compiler and has no presentation logic.
"""

from engine.discovery.compiler import DiscoveryCompiler
from engine.discovery.model import (
    Discovery,
    DiscoveryFact,
    DiscoveryKind,
    DiscoveryModel,
    DiscoveryReference,
)

__all__ = [
    "Discovery",
    "DiscoveryCompiler",
    "DiscoveryFact",
    "DiscoveryKind",
    "DiscoveryModel",
    "DiscoveryReference",
]
