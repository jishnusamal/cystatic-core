"""Java configuration extractor - discovers environment variable and config references."""

import re
from typing import Any

from engine.language.base import BaseExtractor


class JavaConfigurationExtractor(BaseExtractor):
    """
    Extracts configuration references from Java source files.

    Recognizes:
    - @Value annotations (Spring)
    - @ConfigurationProperties (Spring Boot)
    - System.getenv() calls
    - System.getProperty() calls
    - Environment.getProperty() calls
    - Feature flag checks

    Produces a list of dicts with keys: symbol_id, config_key, kind,
    framework, file, line, default_value.
    """

    def extract(self, tree: list[str], file_path: str) -> list[dict[str, Any]]:
        """
        Extract configuration references from a Java source file.

        Args:
            tree: List of lines from the source file
            file_path: Path to the source file

        Returns:
            List of configuration reference dicts
        """
        config_refs = []
        content = "\n".join(tree)

        # Spring @Value annotations
        for match in re.finditer(r'@Value\s*\(\s*["\']\$\{([^}]+)\}["\']', content):
            config_key = match.group(1)
            caller_id = self._find_method_for_line(
                tree, content[: match.start()].count("\n")
            )
            default_value = ""
            # Check for default value in ${key:default} syntax
            if ":" in config_key:
                parts = config_key.split(":", 1)
                config_key = parts[0]
                default_value = parts[1]

            config_refs.append(
                {
                    "symbol_id": caller_id or "",
                    "config_key": config_key,
                    "kind": "environment_variable",
                    "framework": "spring",
                    "file": file_path,
                    "line": content[: match.start()].count("\n") + 1,
                    "default_value": default_value,
                }
            )

        # System.getenv() calls
        for match in re.finditer(r'System\.getenv\s*\(\s*"([^"]+)"', content):
            caller_id = self._find_method_for_line(
                tree, content[: match.start()].count("\n")
            )

            config_refs.append(
                {
                    "symbol_id": caller_id or "",
                    "config_key": match.group(1),
                    "kind": "environment_variable",
                    "framework": "java",
                    "file": file_path,
                    "line": content[: match.start()].count("\n") + 1,
                    "default_value": "",
                }
            )

        # System.getProperty() calls
        for match in re.finditer(r'System\.getProperty\s*\(\s*"([^"]+)"', content):
            caller_id = self._find_method_for_line(
                tree, content[: match.start()].count("\n")
            )

            config_refs.append(
                {
                    "symbol_id": caller_id or "",
                    "config_key": match.group(1),
                    "kind": "environment_variable",
                    "framework": "java",
                    "file": file_path,
                    "line": content[: match.start()].count("\n") + 1,
                    "default_value": "",
                }
            )

        # Environment.getProperty() (Spring)
        for match in re.finditer(
            r'(?:env|environment|env\.getProperty)\s*\(\s*"([^"]+)"', content
        ):
            caller_id = self._find_method_for_line(
                tree, content[: match.start()].count("\n")
            )

            config_refs.append(
                {
                    "symbol_id": caller_id or "",
                    "config_key": match.group(1),
                    "kind": "environment_variable",
                    "framework": "spring",
                    "file": file_path,
                    "line": content[: match.start()].count("\n") + 1,
                    "default_value": "",
                }
            )

        # @ConfigurationProperties prefix
        for match in re.finditer(
            r'@ConfigurationProperties\s*\(\s*prefix\s*=\s*"([^"]+)"', content
        ):
            config_refs.append(
                {
                    "symbol_id": "",
                    "config_key": match.group(1),
                    "kind": "config_file",
                    "framework": "spring",
                    "file": file_path,
                    "line": content[: match.start()].count("\n") + 1,
                    "default_value": "",
                }
            )

        return config_refs

    def _find_method_for_line(self, lines: list[str], line_idx: int) -> str | None:
        """Find the method enclosing a given line index."""
        method_pattern = r"(?:public|private|protected)?\s*(?:\w+)\s+(\w+)\s*\("
        for i in range(line_idx, -1, -1):
            match = re.search(method_pattern, lines[i])
            if match and "class " not in lines[i] and "interface " not in lines[i]:
                return match.group(1)
        return None
