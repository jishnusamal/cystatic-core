"""TypeScript entrypoint index pass stub."""

from typing import Any
from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass


class TypeScriptEntrypointIndexPass(BaseIndexPass):
    """Stub index pass for TypeScript entrypoints."""

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        pass
