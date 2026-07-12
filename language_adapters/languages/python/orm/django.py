"""Django ORM adapter — provides Django-specific query analysis."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


class DjangoAdapter:
    """Django ORM-specific analysis utilities."""

    # Django model field types
    FIELD_TYPES: Set[str] = {
        "CharField", "IntegerField", "FloatField", "BooleanField",
        "DateField", "DateTimeField", "TextField", "EmailField",
        "URLField", "FileField", "ImageField", "ForeignKey",
        "OneToOneField", "ManyToManyField", "DecimalField",
        "SlugField", "UUIDField", "JSONField", "BinaryField",
        "PositiveIntegerField", "SmallIntegerField", "BigIntegerField",
        "DurationField", "TimeField", "AutoField", "BigAutoField",
        "SmallAutoField", "GenericIPAddressField",
    }

    # Django queryset methods
    QUERYSET_METHODS: Set[str] = {
        "filter", "exclude", "annotate", "aggregate", "count", "exists",
        "prefetch_related", "select_related", "order_by", "distinct",
        "values", "values_list", "only", "defer", "first", "last",
        "in_bulk", "iterator", "latest", "earliest", "reverse",
        "using", "alias",
    }

    # Django model meta options
    META_OPTIONS: Set[str] = {
        "db_table", "ordering", "verbose_name", "verbose_name_plural",
        "unique_together", "index_together", "constraints", "indexes",
    }

    @staticmethod
    def is_django_model(content: str) -> bool:
        """Check if content contains a Django model definition."""
        return "models.Model" in content or "models.Model" in content

    @staticmethod
    def is_django_migration(content: str) -> bool:
        """Check if content is a Django migration file."""
        return "migrations" in content and "Migration" in content

    @staticmethod
    def get_model_name_from_queryset(expr: str) -> Optional[str]:
        """Extract model name from a queryset expression like 'Model.objects.filter()'."""
        parts = expr.split(".")
        if len(parts) >= 2 and parts[1] == "objects":
            return parts[0]
        return None