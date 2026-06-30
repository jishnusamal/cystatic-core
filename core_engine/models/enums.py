"""
Enumerations for core domain models.

Using str enums ensures consistency across analyzers and LLM consumption.
"""
from __future__ import annotations

from enum import Enum


class SymbolKind(str, Enum):
    """Classification of a code symbol."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    VARIABLE = "variable"
    CONSTANT = "constant"


class RiskAnchorType(str, Enum):
    """Categories of changes known to increase downstream uncertainty."""
    MONEY_FLOW = "money_flow"
    TRANSACTION_BOUNDARY = "transaction_boundary"
    STATE_MUTATION = "state_mutation"
    RETRY_SENSITIVE = "retry_sensitive"
    EXTERNAL_DEPENDENCY = "external_dependency"
    AUTHENTICATION = "authentication"
    CACHE_CONSISTENCY = "cache_consistency"


class EvidenceType(str, Enum):
    """Types of deterministic evidence connecting two entities."""
    SAME_MODULE = "same_module"
    SAME_CLASS = "same_class"
    SAME_SERVICE = "same_service"
    SHARED_BUSINESS_OBJECT = "shared_business_object"
    SHARED_TRANSACTION = "shared_transaction"
    SHARED_DATABASE_TABLE = "shared_database_table"
    EVENT_PUBLICATION = "event_publication"
    EVENT_CONSUMPTION = "event_consumption"
    CANONICAL_REQUEST_FLOW = "canonical_request_flow"
    OWNERSHIP_RELATIONSHIP = "ownership_relationship"
    DOMAIN_RELATIONSHIP = "domain_relationship"
    RETRY_INTERACTION = "retry_interaction"
    CACHE_DEPENDENCY = "cache_dependency"
    SYMBOL_REFERENCE = "symbol_reference"