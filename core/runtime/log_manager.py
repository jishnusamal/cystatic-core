"""Backward-compatibility shim. Import from core.logging instead."""
from core.logging import LogManager
__all__ = ["LogManager"]
