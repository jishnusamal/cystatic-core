"""Language detection and adapter factory."""

from runtime.language.detection import (
    LanguageAdapterFactory,
    get_language_factory,
)

__all__ = [
    "LanguageAdapterFactory",
    "get_language_factory",
]