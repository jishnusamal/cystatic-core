"""Language-agnostic node types for the semantic graph."""

from __future__ import annotations

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class NodeType(Enum):
    FUNCTION = auto()
    METHOD = auto()
    CLASS = auto()
    MODULE = auto()
    DECORATOR = auto()
    ENDPOINT = auto()
    MODEL = auto()
    FIELD = auto()
    TABLE = auto()
    COLUMN = auto()
    QUERY = auto()
    TRANSACTION = auto()
    MIGRATION = auto()
    TEST = auto()
    EVENT = auto()
    EXTERNAL_SERVICE = auto()
    CACHE = auto()
    QUEUE = auto()


@dataclass
class BaseNode:
    """Base class for all semantic graph nodes."""

    node_type: Optional[NodeType] = None
    name: str = ""
    file_path: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    change_type: str = "modified"  # added, modified, deleted, renamed

    def __hash__(self) -> int:
        return hash((self.node_type, self.name, self.file_path))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseNode):
            return NotImplemented
        return (
            self.node_type == other.node_type
            and self.name == other.name
            and self.file_path == other.file_path
        )

    def __lt__(self, other: BaseNode) -> bool:
        """Support sorting for deduplication."""
        return (self.node_type, self.name, self.file_path) < (other.node_type, other.name, other.file_path)


@dataclass
class FunctionNode(BaseNode):
    """Represents a function definition."""

    is_async: bool = False
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    visibility: str = "public"  # public, private, protected
    decorators: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    return_type: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    _node_type_override: NodeType = NodeType.FUNCTION

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class MethodNode(BaseNode):
    """Represents a method definition within a class."""

    class_name: str = ""
    is_async: bool = False
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    visibility: str = "public"
    decorators: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    return_type: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    _node_type_override: NodeType = NodeType.METHOD

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class ClassNode(BaseNode):
    """Represents a class definition."""

    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    _node_type_override: NodeType = NodeType.CLASS

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class ModuleNode(BaseNode):
    """Represents a Python module (file)."""

    docstring: Optional[str] = None
    _node_type_override: NodeType = NodeType.MODULE

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class DecoratorNode(BaseNode):
    """Represents a decorator applied to a function/method/class."""

    target_name: str = ""
    arguments: list[str] = field(default_factory=list)
    _node_type_override: NodeType = NodeType.DECORATOR

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class EndpointNode(BaseNode):
    """Represents an HTTP endpoint."""

    method: str = "GET"  # GET, POST, PUT, DELETE, PATCH, etc.
    route: str = ""
    framework: str = ""  # fastapi, flask
    handler_function: str = ""
    _node_type_override: NodeType = NodeType.ENDPOINT

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class ModelNode(BaseNode):
    """Represents an ORM model (Django Model, SQLAlchemy declarative)."""

    table_name: Optional[str] = None
    orm: str = ""  # django, sqlalchemy
    bases: list[str] = field(default_factory=list)
    _node_type_override: NodeType = NodeType.MODEL

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class FieldNode(BaseNode):
    """Represents a model field / database column."""

    model_name: str = ""
    field_type: str = ""
    nullable: bool = True
    has_default: bool = False
    is_primary_key: bool = False
    is_unique: bool = False
    is_indexed: bool = False
    is_foreign_key: bool = False
    references: Optional[str] = None
    _node_type_override: NodeType = NodeType.FIELD

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class TableNode(BaseNode):
    """Represents a database table (from migrations)."""

    _node_type_override: NodeType = NodeType.TABLE

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class ColumnNode(BaseNode):
    """Represents a database column (from migrations)."""

    table_name: str = ""
    column_type: str = ""
    nullable: bool = True
    has_default: bool = False
    is_primary_key: bool = False
    is_unique: bool = False
    is_indexed: bool = False
    _node_type_override: NodeType = NodeType.COLUMN

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class QueryNode(BaseNode):
    """Represents a database query operation."""

    operation: str = ""  # filter, exclude, annotate, aggregate, count, exists, raw
    target_model: str = ""
    filters: list[str] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    projection: list[str] = field(default_factory=list)
    changed_filters: list[str] = field(default_factory=list)
    changed_group_by: list[str] = field(default_factory=list)
    changed_projection: list[str] = field(default_factory=list)
    _node_type_override: NodeType = NodeType.QUERY

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class TransactionNode(BaseNode):
    """Represents a database transaction boundary."""

    scope: str = ""  # function, method, context_manager
    is_nested: bool = False
    operations: list[str] = field(default_factory=list)
    _node_type_override: NodeType = NodeType.TRANSACTION

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class MigrationNode(BaseNode):
    """Represents a database migration."""

    operations: list[dict] = field(default_factory=list)  # [{type, table, column, ...}]
    _node_type_override: NodeType = NodeType.MIGRATION

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class TestNode(BaseNode):
    """Represents a test case."""

    test_type: str = "unit"  # unit, integration, e2e, api
    framework: str = "pytest"
    target_functions: list[str] = field(default_factory=list)
    uses_database: bool = False
    uses_mock: bool = False
    uses_fixtures: list[str] = field(default_factory=list)
    is_parametrized: bool = False
    _node_type_override: NodeType = NodeType.TEST

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class EventNode(BaseNode):
    """Represents an event (published or subscribed)."""

    event_type: str = ""  # kafka, redis, celery, webhook, etc.
    _node_type_override: NodeType = NodeType.EVENT

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class ExternalServiceNode(BaseNode):
    """Represents an external service call (HTTP, SDK, etc.)."""

    service_type: str = ""  # stripe, sendgrid, aws, etc.
    protocol: str = "http"  # http, sdk, smtp, etc.
    _node_type_override: NodeType = NodeType.EXTERNAL_SERVICE

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class CacheNode(BaseNode):
    """Represents a cache operation."""

    cache_type: str = ""  # redis, memcached, django_cache, etc.
    operation: str = ""  # get, set, delete, invalidate
    _node_type_override: NodeType = NodeType.CACHE

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')


@dataclass
class QueueNode(BaseNode):
    """Represents a queue operation."""

    queue_type: str = ""  # celery, rabbitmq, sqs, etc.
    operation: str = ""  # publish, consume, delay
    _node_type_override: NodeType = NodeType.QUEUE

    def __post_init__(self) -> None:
        self.node_type = self._node_type_override
        object.__delattr__(self, '_node_type_override')
