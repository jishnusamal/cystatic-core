"""Deterministic rules — each produces signals from the semantic graph.

Every rule is an independent module implementing the Rule interface.
Rules never depend on one another.
"""

from core_engine.rules.base import Rule, RuleResult
from core_engine.rules.validation import ValidationRule
from core_engine.rules.persistence import PersistenceRule
from core_engine.rules.queries import QueryRule
from core_engine.rules.transactions import TransactionRule
from core_engine.rules.migrations import MigrationRule
from core_engine.rules.api import APIExposureRule
from core_engine.rules.events import EventRule
from core_engine.rules.cache import CacheRule
from core_engine.rules.auth import AuthRule
from core_engine.rules.external_dependency import ExternalDependencyRule
from core_engine.rules.cross_domain import CrossDomainRule
from core_engine.rules.coverage import CoverageRule

__all__ = [
    "Rule",
    "RuleResult",
    "ValidationRule",
    "PersistenceRule",
    "QueryRule",
    "TransactionRule",
    "MigrationRule",
    "APIExposureRule",
    "EventRule",
    "CacheRule",
    "AuthRule",
    "ExternalDependencyRule",
    "CrossDomainRule",
    "CoverageRule",
]
