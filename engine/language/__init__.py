"""Language adapters package - compiles source code to RepositoryModel."""

from core.errors import LanguageRegistrationError

from .base import BaseLanguageAdapter
from .builtins import create_default_language_registry
from .detection import (
    LanguageAdapterFactory,
    LanguageDetector,
    get_language_factory,
)
from .java import JavaLanguageAdapter
from .python import PythonLanguageAdapter
from .registry import LanguageRegistry

__all__ = [
    "BaseLanguageAdapter",
    "JavaLanguageAdapter",
    "LanguageAdapterFactory",
    "LanguageDetector",
    "LanguageRegistrationError",
    "LanguageRegistry",
    "PythonLanguageAdapter",
    "create_default_language_registry",
    "get_language_factory",
]
