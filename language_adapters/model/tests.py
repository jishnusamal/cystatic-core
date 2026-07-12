"""Test models - test definitions discovered in the repository."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .evidence import Evidence


class TestFramework(str, Enum):
    """Test framework identifier."""
    PYTEST = "pytest"
    UNITTEST = "unittest"
    DOCTEST = "doctest"
    JUNIT = "junit"
    TESTNG = "testng"
    MOCKITO = "mockito"
    CUCUMBER = "cucumber"
    OTHER = "other"


@dataclass(frozen=True)
class TestFixture:
    """
    Represents a test fixture discovered in the repository.

    Attributes:
        name: Fixture name
        scope: Fixture scope (function, class, module, session)
        symbol_id: Symbol id of the fixture function
        file: Source file where the fixture is defined
        line: Line number where the fixture is defined
    """
    name: str
    scope: str = "function"
    symbol_id: str = ""
    file: str = ""
    line: int = 0


@dataclass(frozen=True)
class TestDefinition:
    """
    Represents a test class or test method discovered in the repository.

    Attributes:
        symbol_id: Symbol id of the test class/method
        name: Test name
        kind: Type of test definition (class, method, function)
        framework: Test framework
        file: Source file where the test is defined
        line: Line number where the test is defined
        fixtures: List of fixtures used by this test
        assertions: List of assertion types used
        evidence: Provenance evidence for this test definition
        metadata: Additional framework-specific metadata
    """
    symbol_id: str
    name: str
    kind: str = "function"  # class, method, function
    framework: TestFramework = TestFramework.OTHER
    file: str = ""
    line: int = 0
    fixtures: tuple[TestFixture, ...] = field(default_factory=tuple)
    assertions: tuple[str, ...] = field(default_factory=tuple)
    evidence: Evidence | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate test definition after initialization."""
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")
        if not self.name:
            raise ValueError("Test name cannot be empty")
        if isinstance(self.framework, str):
            object.__setattr__(self, 'framework', TestFramework(self.framework))
        if isinstance(self.fixtures, list):
            object.__setattr__(self, 'fixtures', tuple(self.fixtures))
        if isinstance(self.assertions, list):
            object.__setattr__(self, 'assertions', tuple(self.assertions))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))