"""Interfaces for language adapters."""

from language_adapters.interfaces.adapter import LanguageAdapter
from language_adapters.interfaces.graph import GraphBuilder

__all__ = ["LanguageAdapter", "GraphBuilder"]