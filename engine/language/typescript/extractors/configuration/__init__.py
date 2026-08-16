"""TypeScript configuration extractor stub."""

from typing import Any
from engine.language.base import BaseExtractor


class TypeScriptConfigurationExtractor(BaseExtractor):
    """Stub extractor for TypeScript configurations."""

    def extract(self, tree: Any, file_path: str) -> list[dict[str, Any]]:
        return []
