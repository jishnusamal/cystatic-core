"""Java type relationship extractor - extracts inheritance, implementation, and composition."""

import re
from typing import Any

from engine.language.base import BaseExtractor


class JavaTypeExtractor(BaseExtractor):
    """
    Extracts type relationships from Java source files.

    Discovers:
    - Class inheritance (extends)
    - Interface implementation (implements)
    - Composition relationships (field types)
    - Generic type references

    Produces a list of dicts with keys: source_sym, target_sym, relation_type, metadata.
    """

    def extract(self, tree: list[str], file_path: str) -> list[dict[str, Any]]:
        """
        Extract all type relationships from a Java source file.

        Args:
            tree: List of lines from the source file
            file_path: Path to the source file

        Returns:
            List of relationship dicts
        """
        relationships = []
        content = "\n".join(tree)

        class_pattern = (
            r"(?:public|private|protected)?\s*(?:abstract|final)?\s*(?:class|interface|enum)\s+(\w+)"
            r"(?:\s+extends\s+(\w+(?:\.\w+)*))?"
            r"(?:\s+implements\s+([^{]+))?"
        )

        for match in re.finditer(class_pattern, content, re.MULTILINE):
            class_name = match.group(1)
            source_sym = f"java://{file_path}#{class_name}"

            # Inheritance (extends)
            extends_name = match.group(2)
            if extends_name:
                relationships.append(
                    {
                        "source_sym": source_sym,
                        "target_sym": extends_name,
                        "relation_type": "extends",
                        "metadata": {"file": file_path},
                    }
                )

            # Interface implementation (implements)
            implements_names = match.group(3)
            if implements_names:
                for iface in re.split(r"\s*,\s*", implements_names.strip()):
                    iface = iface.strip()
                    if iface:
                        relationships.append(
                            {
                                "source_sym": source_sym,
                                "target_sym": iface,
                                "relation_type": "implements",
                                "metadata": {"file": file_path},
                            }
                        )

        # Composition from field declarations
        for i, line in enumerate(tree, 1):
            if self._is_inside_class(tree, i - 1):
                field_match = re.search(
                    r"(?:private|public|protected)?\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*;",
                    line,
                )
                if field_match:
                    field_type = field_match.group(1)
                    field_name = field_match.group(2)

                    # Skip primitives and common types
                    if field_type.lower() in (
                        "int",
                        "long",
                        "double",
                        "float",
                        "boolean",
                        "string",
                        "void",
                        "byte",
                        "short",
                        "char",
                    ):
                        continue

                    class_name = self._find_enclosing_class(tree, i - 1)
                    if class_name:
                        source_sym = f"java://{file_path}#{class_name}"
                        relationships.append(
                            {
                                "source_sym": source_sym,
                                "target_sym": field_type,
                                "relation_type": "composes",
                                "metadata": {
                                    "field": field_name,
                                    "file": file_path,
                                    "line": i,
                                },
                            }
                        )

        return relationships

    def _is_inside_class(self, lines: list[str], line_idx: int) -> bool:
        """Check if a line is inside a class definition."""
        if line_idx < 0 or line_idx >= len(lines):
            return False
        open_braces = 0
        for i in range(line_idx):
            line = lines[i]
            open_braces += line.count("{") - line.count("}")
        return open_braces > 0

    def _find_enclosing_class(self, lines: list[str], line_idx: int) -> str | None:
        """Find the name of the class enclosing a line."""
        class_pattern = (
            r"(?:public|private|protected)?\s*(?:abstract|final)?\s*class\s+(\w+)"
        )
        for i in range(line_idx, -1, -1):
            match = re.search(class_pattern, lines[i])
            if match:
                # Check if the line is inside this class
                brace_count = 0
                for j in range(i, line_idx):
                    brace_count += lines[j].count("{") - lines[j].count("}")
                if brace_count > 0:
                    return match.group(1)
        return None
