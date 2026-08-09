"""Java entrypoint index pass - detects REST API endpoints from Spring annotations.

Emits only structural entrypoint facts. No handler resolution, no graph construction.
"""

import re
from typing import Any

from language_adapters.base.file_context import FileContext
from language_adapters.base.passes import BaseIndexPass
from engine.repository.model.repository_index import EntrypointEntry


class JavaEntrypointIndexPass(BaseIndexPass):
    """Index pass that extracts entrypoint facts from Java source.

    Extracts: route, handler name, HTTP method, framework, line number.
    No resolution of what the handler refers to - that's semantic compilation.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract entrypoints from a Java file context."""
        lines = context.ast
        file_path = context.path

        endpoint_patterns = [
            (r'@RequestMapping\s*\(.*?value\s*=\s*"([^"]+)"', None),
            (r'@GetMapping\s*\(.*?"([^"]+)"', 'GET'),
            (r'@PostMapping\s*\(.*?"([^"]+)"', 'POST'),
            (r'@PutMapping\s*\(.*?"([^"]+)"', 'PUT'),
            (r'@DeleteMapping\s*\(.*?"([^"]+)"', 'DELETE'),
            (r'@PatchMapping\s*\(.*?"([^"]+)"', 'PATCH'),
        ]

        for i, line in enumerate(lines, 1):
            for pattern, method in endpoint_patterns:
                match = re.search(pattern, line)
                if match:
                    route = match.group(1)
                    handler_name = self._find_method_name(lines, i - 1)

                    if handler_name:
                        builder["entrypoints"].append(
                            EntrypointEntry(
                                route=f"{method or 'GET'} {route}",
                                handler=handler_name,
                                kind="rest_endpoint",
                                framework="spring",
                                file=file_path,
                                line=i,
                            )
                        )

    def _find_method_name(self, lines: list[str], start_idx: int) -> str | None:
        """Find the method name following an annotation."""
        method_pattern = r'(public|private|protected)?\s*\w+\s+(\w+)\s*\('

        for i in range(start_idx, min(start_idx + 5, len(lines))):
            match = re.search(method_pattern, lines[i])
            if match and 'class ' not in lines[i]:
                return match.group(2)

        return None