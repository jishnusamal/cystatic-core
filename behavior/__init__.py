"""Backward-compatibility shim. New code should import from engine.behavior."""
from engine.behavior.model import BehaviorModel
__all__ = ["BehaviorModel"]
