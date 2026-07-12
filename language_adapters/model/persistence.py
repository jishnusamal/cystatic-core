"""Persistence models - ORM/ODM constructs discovered in the repository."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PersistenceModelKind(str, Enum):
    """Type of persistence model."""
    TABLE = "table"
    COLLECTION = "collection"
    VIEW = "view"
    DOCUMENT = "document"


class RepositoryMethodKind(str, Enum):
    """Type of repository/data access method."""
    FIND = "find"
    SAVE = "save"
    UPDATE = "update"
    DELETE = "delete"
    QUERY = "query"
    COUNT = "count"
    EXISTS = "exists"
    CUSTOM = "custom"


@dataclass(frozen=True)
class PersistenceModel:
    """
    Represents an ORM/ODM persistence model discovered in the repository.

    Examples: SQLAlchemy models, Django ORM models, Hibernate entities, JPA entities.

    Attributes:
        symbol_id: Symbol id of the model class
        name: Model name
        kind: Type of persistence model
        table_name: Underlying table or collection name
        framework: ORM/ODM framework (sqlalchemy, django, hibernate, jpa)
        fields: List of field definitions
        relationships: List of relationship definitions
        metadata: Additional framework-specific metadata
    """
    symbol_id: str
    name: str
    kind: PersistenceModelKind = PersistenceModelKind.TABLE
    table_name: str = ""
    framework: str = ""
    fields: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    relationships: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate persistence model after initialization."""
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")
        if not self.name:
            raise ValueError("Model name cannot be empty")
        if isinstance(self.kind, str):
            object.__setattr__(self, 'kind', PersistenceModelKind(self.kind))
        if isinstance(self.fields, list):
            object.__setattr__(self, 'fields', tuple(self.fields))
        if isinstance(self.relationships, list):
            object.__setattr__(self, 'relationships', tuple(self.relationships))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))


@dataclass(frozen=True)
class RepositoryMethod:
    """
    Represents a repository/data access method.

    Examples: Spring Data JPA repository methods, custom DAO methods.

    Attributes:
        symbol_id: Symbol id of the method
        name: Method name
        kind: Type of repository method
        model_symbol_id: Symbol id of the associated model
        framework: Framework identifying the repository system
        query: Underlying query if available
        metadata: Additional framework-specific metadata
    """
    symbol_id: str
    name: str
    kind: RepositoryMethodKind = RepositoryMethodKind.CUSTOM
    model_symbol_id: str = ""
    framework: str = ""
    query: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate repository method after initialization."""
        if not self.symbol_id:
            raise ValueError("Symbol id cannot be empty")
        if not self.name:
            raise ValueError("Method name cannot be empty")
        if isinstance(self.kind, str):
            object.__setattr__(self, 'kind', RepositoryMethodKind(self.kind))
        if isinstance(self.metadata, dict):
            object.__setattr__(self, 'metadata', dict(self.metadata))