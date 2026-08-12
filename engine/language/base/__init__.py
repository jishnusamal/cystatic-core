"""Base language adapter package.

Architecture:
    Repository → LanguageAdapter → RepositoryIndex → SemanticCompiler → RepositoryModel

    The LanguageAdapter only extracts structural facts (RepositoryIndex).
    The SemanticCompiler performs all semantic reasoning (resolved relationships).
"""

from .adapter import BaseLanguageAdapter
from .index_compiler import IndexCompiler
from .semantic_compiler import SemanticCompiler
from .file_context import FileContext
from .passes import BaseIndexPass
from .parser import BaseParser

__all__ = [
    "BaseLanguageAdapter",
    "IndexCompiler",
    "SemanticCompiler",
    "FileContext",
    "BaseIndexPass",
    "BaseParser",
]
