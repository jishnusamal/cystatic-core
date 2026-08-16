"""TypeScript call extractor stub."""

from typing import Any
from engine.language.base import BaseExtractor


class TypeScriptCallExtractor(BaseExtractor):
    """Stub extractor for TypeScript calls."""

    def extract(self, tree: Any, file_path: str) -> list[dict[str, Any]]:
        return []
