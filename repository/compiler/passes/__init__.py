"""Compiler passes package."""

from .base import CompilerPass, PassContext
from .symbol_collection.impl import SymbolCollectionPass
from .reference_resolution.impl import ReferenceResolutionPass
from .call_graph.impl import CallGraphPass
from .endpoint_discovery.impl import EndpointDiscoveryPass

__all__ = [
    "CompilerPass",
    "PassContext",
    "SymbolCollectionPass",
    "ReferenceResolutionPass",
    "CallGraphPass",
    "EndpointDiscoveryPass",
]
