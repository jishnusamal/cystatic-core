"""Change types for classification."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FunctionBodyChange:
    """Function body was modified."""
    old_body_hash: str
    new_body_hash: str


@dataclass(frozen=True)
class SignatureChange:
    """Function/method signature changed."""
    old_signature: str
    new_signature: str
    changes: tuple[str, ...] = field(default_factory=tuple)  # e.g., ("parameter_added", "return_type_changed")


@dataclass(frozen=True)
class VisibilityChange:
    """Symbol visibility changed."""
    old_visibility: str
    new_visibility: str


@dataclass(frozen=True)
class DecoratorChange:
    """Decorator/annotation changed."""
    old_decorators: tuple[str, ...]
    new_decorators: tuple[str, ...]


@dataclass(frozen=True)
class SuperclassChange:
    """Class superclass changed."""
    old_superclass: str | None
    new_superclass: str | None


@dataclass(frozen=True)
class InterfaceChange:
    """Implemented interfaces changed."""
    old_interfaces: tuple[str, ...]
    new_interfaces: tuple[str, ...]


@dataclass(frozen=True)
class EndpointAnnotationChange:
    """Endpoint annotation changed."""
    old_endpoint: str | None
    new_endpoint: str | None
    old_method: str | None
    new_method: str | None