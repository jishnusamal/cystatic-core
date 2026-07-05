"""Risk flags — shared enums used by the core engine and schemas."""

from __future__ import annotations

from enum import Enum, auto


class SignalType(Enum):
    """Types of signals that can be detected from code changes."""

    VALIDATION = auto()
    PERSISTENCE = auto()
    TRANSACTION = auto()
    QUERY = auto()
    MIGRATION = auto()
    API = auto()
    EVENT = auto()
    CACHE = auto()
    AUTH = auto()
    EXTERNAL_DEPENDENCY = auto()
    CROSS_DOMAIN = auto()
    COVERAGE = auto()
    ARCHITECTURE = auto()


class RiskEventType(Enum):
    """Types of risk events that can be flagged."""

    VALIDATION_CHANGED = auto()
    PERSISTENCE_CHANGED = auto()
    TRANSACTION_CHANGED = auto()
    QUERY_CHANGED = auto()
    MIGRATION_ADDED = auto()
    API_CHANGED = auto()
    EVENT_CHANGED = auto()
    CACHE_CHANGED = auto()
    AUTH_CHANGED = auto()
    EXTERNAL_DEPENDENCY_CHANGED = auto()
    CROSS_DOMAIN_CHANGED = auto()
    UNTESTED_CODE = auto()
    ARCHITECTURE_CHANGED = auto()