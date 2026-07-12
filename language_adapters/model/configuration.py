"""Configuration models - configuration references discovered in the repository."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConfigReferenceKind(str, Enum):
    """Type of configuration reference."""
    ENVIRONMENT_VARIABLE = "environment_variable"
    CONFIG_FILE = "config_file"
    FEATURE_FLAG = "feature_flag"
    SETTINGS_OBJECT = "settings_object"
    PROPERTY_FILE = "property_file"


@dataclass(frozen=True)
class ConfigurationReference:
    """
    Represents a configuration reference discovered in the repository.

    Examples: os.environ['DB_URL'], @Value('${app.name}'), settings.DATABASE_URL.

    Attributes:
        symbol_id: Symbol id of the referencing function/method
        config_key: The configuration key or name being referenced
        kind: Type of configuration reference
        framework: Framework or library used for configuration
        file: Source file where the reference occurs
        line: Line number where the reference occurs
        default_value: Default value if specifiable in code
        metadata: Additional framework-specific metadata
    """
    symbol_id: str
    config_key: str
    kind: ConfigReferenceKind = ConfigReferenceKind.ENVIRONMENT_VARIABLE
    framework: str = ""
    file: str = ""
    line: int = 0
    default_value: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration reference after initialization."""
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")
        if not self.config_key:
            raise ValueError("Config key cannot be empty")
        if isinstance(self.kind, str):
            object.__setattr__(self, 'kind', ConfigReferenceKind(self.kind))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))