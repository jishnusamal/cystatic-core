"""Base language adapter package.

Architecture:
    Repository → LanguageAdapter → RepositoryIndex → SemanticCompiler → RepositoryModel

    The LanguageAdapter only extracts structural facts (RepositoryIndex).
    The SemanticCompiler performs all semantic reasoning (resolved relationships).
"""

from .adapter import BaseLanguageAdapter
from .file_context import FileContext
from .index_compiler import IndexCompiler
from .parser import BaseParser
from .passes import BaseIndexPass
from .semantic_compiler import SemanticCompiler
from .spec import LanguageSpec

__all__ = [
    "BaseIndexPass",
    "BaseLanguageAdapter",
    "BaseParser",
    "FileContext",
    "IndexCompiler",
    "LanguageSpec",
    "SemanticCompiler",
]
