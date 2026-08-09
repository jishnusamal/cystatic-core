"""Backward-compatibility shim. New code should import from engine.operational."""
from engine.operational.model import OperationalChangeModel
from engine.operational.discovery import DiscoveryCompiler
__all__ = ["OperationalChangeModel", "DiscoveryCompiler"]
