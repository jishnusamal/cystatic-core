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
    GENERIC = "generic"
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

    # Ownership evidence types
    OWNED_BY = "owned_by"
    SAME_OWNER = "same_owner"
    CROSS_OWNER = "cross_owner"

    # Domain hub evidence types
    BELONGS_TO_DOMAIN = "belongs_to_domain"
    TOUCHES_DOMAIN = "touches_domain"
    CROSS_DOMAIN_RELATIONSHIP = "cross_domain_relationship"
    SHARED_DOMAIN = "shared_domain"

    # Business object evidence types
    BUSINESS_OBJECT_REFERENCE = "business_object_reference"

    # Operational constraint evidence types
    OPERATIONAL_CONSTRAINT = "operational_constraint"

    # Service relationship evidence types
    DEPENDS_ON_SERVICE = "depends_on_service"

    # External dependency evidence types
    CALLS_EXTERNAL_SYSTEM = "calls_external_system"
    SHARED_EXTERNAL_SYSTEM = "shared_external_system"
    DEPENDS_ON_PROVIDER = "depends_on_provider"

    # Transaction boundary evidence types
    STARTS_TRANSACTION = "starts_transaction"
    COMMITS_TRANSACTION = "commits_transaction"
    ROLLS_BACK_TRANSACTION = "rolls_back_transaction"
    INSIDE_TRANSACTION = "inside_transaction"

    # Database relationship evidence types
    READS_TABLE = "reads_table"
    WRITES_TABLE = "writes_table"
    SHARES_TABLE = "shares_table"

    # Naming similarity evidence types
    NAMING_SIMILARITY = "naming_similarity"

    # Event relationship evidence types
    PUBLISHES_EVENT = "publishes_event"
    CONSUMES_EVENT = "consumes_event"
    SHARED_EVENT = "shared_event"
    SHARED_EVENT_PUBLICATION = "shared_event_publication"
    SHARED_EVENT_CONSUMPTION = "shared_event_consumption"
    EVENT_PUBLICATION_CONSUMPTION = "event_publication_consumption"

    # Cache dependency evidence types
    READS_CACHE = "reads_cache"
    SHARED_CACHE = "shared_cache"

    # Endpoint relationship evidence types
    ENDPOINT_IMPLEMENTATION = "endpoint_implementation"
    REST_ENDPOINT = "rest_endpoint"
    GRAPHQL_ENDPOINT = "graphql_endpoint"
    GRPC_ENDPOINT = "grpc_endpoint"
    CLI_ENDPOINT = "cli_endpoint"
    SCHEDULED_ENDPOINT = "scheduled_endpoint"