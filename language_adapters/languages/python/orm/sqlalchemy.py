"""SQLAlchemy ORM adapter — provides SQLAlchemy-specific query analysis."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


class SQLAlchemyAdapter:
    """SQLAlchemy ORM-specific analysis utilities."""

    # SQLAlchemy column types
    COLUMN_TYPES: Set[str] = {
        "Integer", "String", "Float", "Boolean", "DateTime", "Date",
        "Time", "Text", "Binary", "LargeBinary", "Numeric", "Decimal",
        "SmallInteger", "BigInteger", "Unicode", "UnicodeText",
        "PickleType", "Interval", "Enum", "JSON", "ARRAY",
    }

    # SQLAlchemy query methods
    QUERY_METHODS: Set[str] = {
        "filter", "filter_by", "all", "first", "one", "one_or_none",
        "get", "count", "order_by", "limit", "offset", "join",
        "outerjoin", "subquery", "from_statement", "with_entities",
        "group_by", "having", "distinct", "exists",
    }

    # SQLAlchemy session methods
    SESSION_METHODS: Set[str] = {
        "add", "add_all", "delete", "flush", "commit", "rollback",
        "execute", "scalar", "scalars",
    }

    @staticmethod
    def is_sqlalchemy_model(content: str) -> bool:
        """Check if content contains a SQLAlchemy model definition."""
        return "declarative_base" in content or "Base" in content

    @staticmethod
    def is_sqlalchemy_session(content: str) -> bool:
        """Check if content uses SQLAlchemy sessions."""
        return "Session" in content or "session" in content

    @staticmethod
    def extract_table_name(model_name: str) -> str:
        """Convert a model class name to a table name (snake_case convention)."""
        result: List[str] = []
        for i, char in enumerate(model_name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)