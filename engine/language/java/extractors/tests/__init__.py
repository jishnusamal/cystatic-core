"""Java test extractor - discovers test classes, methods, and fixtures."""

import re
from typing import Any, ClassVar

from engine.language.base import BaseExtractor


class JavaTestExtractor(BaseExtractor):
    """
    Extracts test definitions from Java source files.

    Recognizes:
    - JUnit 4/5 test classes and methods
    - TestNG test classes and methods
    - Mockito usage
    - Test fixtures (@Before, @BeforeEach, @After, @AfterEach)

    Produces a list of dicts with keys: symbol_id, name, kind, framework,
    file, line, fixtures, assertions.
    """

    JUNIT4_ANNOTATIONS: ClassVar[set[str]] = {
        "@Test",
        "@Before",
        "@After",
        "@BeforeClass",
        "@AfterClass",
        "@Ignore",
    }
    JUNIT5_ANNOTATIONS: ClassVar[set[str]] = {
        "@Test",
        "@BeforeEach",
        "@AfterEach",
        "@BeforeAll",
        "@AfterAll",
        "@Disabled",
        "@ParameterizedTest",
    }
    TESTNG_ANNOTATIONS: ClassVar[set[str]] = {
        "@Test",
        "@BeforeMethod",
        "@AfterMethod",
        "@BeforeClass",
        "@AfterClass",
        "@BeforeSuite",
        "@AfterSuite",
    }

    ASSERTION_METHODS: ClassVar[set[str]] = {
        "assertEquals",
        "assertNotEquals",
        "assertTrue",
        "assertFalse",
        "assertNull",
        "assertNotNull",
        "assertSame",
        "assertNotSame",
        "assertThat",
        "assertThrows",
        "assertDoesNotThrow",
        "assertArrayEquals",
        "assertIterableEquals",
        "verify",
        "assertTimeout",
        "assertAll",
    }

    def extract(self, tree: list[str], file_path: str) -> list[dict[str, Any]]:
        """
        Extract test definitions from a Java source file.

        Args:
            tree: List of lines from the source file
            file_path: Path to the source file

        Returns:
            List of test definition dicts
        """
        tests = []
        content = "\n".join(tree)

        # Detect test class
        class_pattern = r"(?:public\s+)?class\s+(\w+)"
        for class_match in re.finditer(class_pattern, content):
            class_name = class_match.group(1)

            if not self._is_test_class(content, class_match.start()):
                continue

            class_symbol_id = f"java://{file_path}#{class_name}"

            # Find class body range
            class_start = class_match.start()
            brace_depth = 0
            in_class = False
            class_line = content[:class_start].count("\n") + 1

            test_methods = []
            for i, line in enumerate(tree):
                if not in_class:
                    if i >= class_line - 1:
                        brace_depth += line.count("{") - line.count("}")
                        if line.count("{") > 0:
                            in_class = True
                    continue

                brace_depth += line.count("{") - line.count("}")
                if brace_depth <= 0:
                    break

                # Check for test method annotations
                test_annotation = self._detect_test_annotation(line)
                if test_annotation and len(tree) > i + 1:
                    # Next line should be the method
                    next_line = tree[i + 1]
                    method_match = re.search(
                        r"(?:public|private|protected)?\s*(?:\w+)\s+(\w+)\s*\(",
                        next_line,
                    )
                    if method_match:
                        method_name = method_match.group(1)
                        method_sym = f"java://{file_path}#{class_name}.{method_name}"
                        assertions = self._find_assertions(tree, i + 1)

                        test_methods.append(
                            {
                                "symbol_id": method_sym,
                                "name": method_name,
                                "kind": "method",
                                "framework": test_annotation,
                                "file": file_path,
                                "line": i + 2,
                                "fixtures": [],
                                "assertions": assertions,
                            }
                        )

            if test_methods or class_name.endswith("Test"):
                tests.append(
                    {
                        "symbol_id": class_symbol_id,
                        "name": class_name,
                        "kind": "class",
                        "framework": self._detect_test_framework(content),
                        "file": file_path,
                        "line": class_line,
                        "fixtures": [],
                        "assertions": [],
                        "test_methods": test_methods,
                    }
                )

        return tests

    def _is_test_class(self, content: str, class_pos: int) -> bool:
        """Check if a class is a test class."""
        # Check for JUnit runner annotation
        if "@RunWith" in content or "@ExtendWith" in content:
            return True

        # Check class name convention
        class_block = content[class_pos : class_pos + 200]
        if re.search(r"class\s+\w+Test", class_block):
            return True

        # Check for test method annotations inside
        for annotation in (
            self.JUNIT4_ANNOTATIONS | self.JUNIT5_ANNOTATIONS | self.TESTNG_ANNOTATIONS
        ):
            if annotation in content[class_pos : class_pos + 1000]:
                return True

        return False

    def _detect_test_annotation(self, line: str) -> str | None:
        """Detect test method annotation and return framework."""
        line = line.strip()
        if line == "@Test":
            return "junit"
        elif line == "@ParameterizedTest":
            return "junit5"
        elif line in self.TESTNG_ANNOTATIONS:
            return "testng"
        return None

    def _detect_test_framework(self, content: str) -> str:
        """Detect the test framework used."""
        if "@Test" in content or "@Before" in content:
            if (
                "@BeforeEach" in content
                or "@AfterEach" in content
                or "@ExtendWith" in content
            ):
                return "junit5"
            return "junit"
        if "TestNG" in content or "@BeforeSuite" in content:
            return "testng"
        return "junit"

    def _find_assertions(self, lines: list[str], start_idx: int) -> list[str]:
        """Find assertion methods in a test method."""
        assertions = set()
        # Simple logic: look for assertion calls within a few lines
        brace_depth = 0
        for i in range(start_idx, min(start_idx + 50, len(lines))):
            line = lines[i]
            brace_depth += line.count("{") - line.count("}")
            if brace_depth < 0:
                break

            for assertion in self.ASSERTION_METHODS:
                if assertion in line:
                    assertions.add(assertion)

        return list(assertions)
