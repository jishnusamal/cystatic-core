"""Base language adapter package.

Architecture:
    Repository → LanguageAdapter → RepositoryIndex → SemanticCompiler → RepositoryModel

    The LanguageAdapter only extracts structural facts (RepositoryIndex).
    The SemanticCompiler performs all semantic reasoning (resolved relationships).
"""

from .adapter import BaseLanguageAdapter
from .capabilities import LanguageCapabilities
from .extractor import BaseExtractor
from .file_context import FileContext
from .index_compiler import IndexCompiler
from .parser import BaseParser
from .passes import BaseIndexPass
from .plugin import LanguagePlugin
from .semantic_compiler import SemanticCompiler
from .spec import LanguageSpec

__all__ = [
    "BaseExtractor",
    "BaseIndexPass",
    "BaseLanguageAdapter",
    "BaseParser",
    "FileContext",
    "IndexCompiler",
    "LanguageCapabilities",
    "LanguagePlugin",
    "LanguageSpec",
    "SemanticCompiler",
]
