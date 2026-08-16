"""TypeScript type extractor stub."""

from typing import Any
from engine.language.base import BaseExtractor


class TypeScriptTypeExtractor(BaseExtractor):
    """Stub extractor for TypeScript types."""

    def extract(self, tree: Any, file_path: str) -> list[dict[str, Any]]:
        return []
