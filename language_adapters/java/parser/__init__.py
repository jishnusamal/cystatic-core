"""Java parser - splits Java source into lines for regex-based extraction."""

from typing import Any

from language_adapters.base.parser import BaseParser


class JavaParser(BaseParser):
    """
    Java source code parser.

    Currently uses a line-splitting approach for regex-based extraction.
    A production version would use a proper Java parser like JavaParser
    or tree-sitter-java to produce a full AST.

    This parser conforms to the BaseParser interface, returning a list of
    lines as the "tree" for the regex-based extractors to process.
    """

    def parse(self, content: str, file_path: str) -> list[str]:
        """
        Parse a Java source file into a list of lines.

        Args:
            content: Raw Java source code
            file_path: Path to the source file

        Returns:
            List of lines from the source file
        """
        return content.split('\n')

    def supports_file(self, file_path: str) -> bool:
        """
        Check if this parser supports a given file.

        Args:
            file_path: Path to the source file

        Returns:
            True if the file ends with .java
        """
        return file_path.endswith('.java')