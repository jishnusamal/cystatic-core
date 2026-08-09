"""Backward-compatibility shim. New code should import from engine.discovery."""
from engine.discovery.compiler import DiscoveryCompiler as EngineeringDiscoveryCompiler
from engine.discovery.model import DiscoveryModel
__all__ = ["EngineeringDiscoveryCompiler", "DiscoveryModel"]
