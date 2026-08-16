"""Language adapters package - compiles source code to RepositoryModel."""

from core.errors import LanguageRegistrationError
from .base import BaseLanguageAdapter
from .detection import (
    LanguageAdapterFactory,
    LanguageDetector,
    get_language_factory,
)
from .java import JavaLanguageAdapter
from .python import PythonLanguageAdapter
from .registry import LanguageRegistry
from .builtins import create_default_language_registry

__all__ = [
    "BaseLanguageAdapter",
    "JavaLanguageAdapter",
    "PythonLanguageAdapter",
    "LanguageRegistry",
    "LanguageDetector",
    "LanguageRegistrationError",
    "create_default_language_registry",
    "get_language_factory",
    "LanguageAdapterFactory",
]
