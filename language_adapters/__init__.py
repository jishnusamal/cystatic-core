"""Backward-compatibility shim. New code should import from engine.language."""
from engine.language.base.adapter import BaseLanguageAdapter
__all__ = ["BaseLanguageAdapter"]
