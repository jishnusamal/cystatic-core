"""Backward-compatibility shim. New code should import from engine.change."""
from engine.change.model import ChangeModel, RepositoryDelta
__all__ = ["ChangeModel", "RepositoryDelta"]
