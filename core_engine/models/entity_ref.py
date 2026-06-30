"""
EntityRef — a reusable reference to any entity in the system.

Used in place of raw strings for `source` and `target` fields,
so evidence can reference symbols, services, endpoints, databases,
queues, events, business objects, and domains with type metadata.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EntityRef(BaseModel):
    """A typed reference to an entity in the system.

    Attributes:
        kind: The type of entity being referenced.
        id: A stable, unique identifier for the entity.
        name: A human-readable name for the entity.
    """
    kind: Literal[
        "symbol",
        "service",
        "endpoint",
        "database",
        "queue",
        "event",
        "business_object",
        "domain",
    ]

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)