"""Java configuration index pass - discovers environment variable and config references.

Emits only structural configuration facts. No resolution, no graph construction.
"""

import re
from typing import Any

from engine.language.base.file_context import FileContext
from engine.language.base.passes import BaseIndexPass
from engine.repository.model.repository_index import ConfigEntry


class JavaConfigurationIndexPass(BaseIndexPass):
    """Index pass that extracts configuration facts from Java source.

    Extracts: config keys, config kind, framework, default values, line number.
    No resolution of what symbols are involved - that's semantic compilation.
    """

    def process(self, context: FileContext, builder: dict[str, Any]) -> None:
        """Extract configuration references from a Java file context."""
        lines = context.ast
        file_path = context.path
        content = '\n'.join(lines)

        # Spring @Value annotations
        for match in re.finditer(r'@Value\s*\(\s*["\']\$\{([^}]+)\}["\']', content):
            config_key = match.group(1)
            default_value = ''
            if ':' in config_key:
                parts = config_key.split(':', 1)
                config_key = parts[0]
                default_value = parts[1]
            line = content[:match.start()].count('\n') + 1
            caller = self._find_method_for_line(lines, line - 1)

            builder["configurations"].append(
                ConfigEntry(
                    symbol_name=caller or "unknown",
                    config_key=config_key,
                    kind="environment_variable",
                    framework="spring",
                    file=file_path,
                    line=line,
                    default_value=default_value,
                )
            )

        # System.getenv() calls
        for match in re.finditer(r'System\.getenv\s*\(\s*"([^"]+)"', content):
            line = content[:match.start()].count('\n') + 1
            caller = self._find_method_for_line(lines, line - 1)

            builder["configurations"].append(
                ConfigEntry(
                    symbol_name=caller or "unknown",
                    config_key=match.group(1),
                    kind="environment_variable",
                    framework="java",
                    file=file_path,
                    line=line,
                )
            )

        # System.getProperty() calls
        for match in re.finditer(r'System\.getProperty\s*\(\s*"([^"]+)"', content):
            line = content[:match.start()].count('\n') + 1
            caller = self._find_method_for_line(lines, line - 1)

            builder["configurations"].append(
                ConfigEntry(
                    symbol_name=caller or "unknown",
                    config_key=match.group(1),
                    kind="environment_variable",
                    framework="java",
                    file=file_path,
                    line=line,
                )
            )

        # Environment.getProperty() (Spring)
        for match in re.finditer(
            r'(?:env|environment|env\.getProperty)\s*\(\s*"([^"]+)"', content,
        ):
            line = content[:match.start()].count('\n') + 1
            caller = self._find_method_for_line(lines, line - 1)

            builder["configurations"].append(
                ConfigEntry(
                    symbol_name=caller or "unknown",
                    config_key=match.group(1),
                    kind="environment_variable",
                    framework="spring",
                    file=file_path,
                    line=line,
                )
            )

        # @ConfigurationProperties prefix
        for match in re.finditer(
            r'@ConfigurationProperties\s*\(\s*prefix\s*=\s*"([^"]+)"', content,
        ):
            line = content[:match.start()].count('\n') + 1

            builder["configurations"].append(
                ConfigEntry(
                    symbol_name="unknown",
                    config_key=match.group(1),
                    kind="config_file",
                    framework="spring",
                    file=file_path,
                    line=line,
                )
            )

    def _find_method_for_line(self, lines: list[str], line_idx: int) -> str | None:
        """Find the method enclosing a given line index."""
        method_pattern = r'(?:public|private|protected)?\s*(?:\w+)\s+(\w+)\s*\('
        for i in range(line_idx, -1, -1):
            match = re.search(method_pattern, lines[i])
            if match and 'class ' not in lines[i] and 'interface ' not in lines[i]:
                return match.group(1)
        return None