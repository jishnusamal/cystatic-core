"""Backward-compatibility shim."""
from engine.language.detection import LanguageAdapterFactory, get_language_factory
__all__ = ["LanguageAdapterFactory", "get_language_factory"]
