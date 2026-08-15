"""Data Compilation Pass - compiles persistent state information.


Question: What persistent state does the behavior affect?

Produces DataModel with:
- Models: data model classes/structs affected
- Tables: database tables referenced
- Reads: symbols that read persistent state
- Writes: symbols that write persistent state
- Transactions: transactional boundaries
- Caches: caching annotations/patterns
- External Storage: references to external storage systems

Everything is directly traceable to repository evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import FrozenSet, cast

from engine.operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from engine.repository.model import RepositoryModel, Symbol, SymbolKind
from engine.operational.model import OperationalChangeModel


@dataclass(frozen=True)
class DataModel:
    """
    Persistent state information for affected behaviors.

    All fields are deterministically derived from the repository model.
    No speculation.
    """

    # Data model symbols (classes/structs representing persistent entities)
    models: tuple[Symbol, ...] = field(default_factory=tuple)

    # Database table names referenced (inferred from ORM annotations, SQL, etc.)
    tables: tuple[str, ...] = field(default_factory=tuple)

    # Symbols that read persistent state (SELECT, GET, query methods)
    reads: tuple[Symbol, ...] = field(default_factory=tuple)

    # Symbols that write persistent state (INSERT, UPDATE, DELETE, save methods)
    writes: tuple[Symbol, ...] = field(default_factory=tuple)

    # Transactional boundaries (symbols with transaction annotations)
    transactions: tuple[Symbol, ...] = field(default_factory=tuple)

    # Cache keys or cache annotations referenced
    caches: tuple[str, ...] = field(default_factory=tuple)

    # External storage references (S3, Redis, etc.) as (storage_type, identifier)
    external_storage: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Convert mutable defaults to immutable types."""
        if isinstance(self.models, list):
            object.__setattr__(self, "models", tuple(self.models))
        if isinstance(self.tables, list):
            object.__setattr__(self, "tables", tuple(self.tables))
        if isinstance(self.reads, list):
            object.__setattr__(self, "reads", tuple(self.reads))
        if isinstance(self.writes, list):
            object.__setattr__(self, "writes", tuple(self.writes))
        if isinstance(self.transactions, list):
            object.__setattr__(self, "transactions", tuple(self.transactions))
        if isinstance(self.caches, list):
            object.__setattr__(self, "caches", tuple(self.caches))
        if isinstance(self.external_storage, list):
            object.__setattr__(self, "external_storage", tuple(self.external_storage))


# Patterns used to infer data operations from symbol properties
_READ_PATTERNS = {
    "get",
    "fetch",
    "load",
    "find",
    "query",
    "select",
    "retrieve",
    "list",
    "search",
    "read",
    "lookup",
    "resolve",
}

_WRITE_PATTERNS = {
    "save",
    "create",
    "update",
    "delete",
    "insert",
    "remove",
    "store",
    "persist",
    "write",
    "put",
    "patch",
    "destroy",
}

_TRANSACTION_PATTERNS = {
    "transaction",
    "transactional",
    "atomic",
    "db_transaction",
}

_CACHE_PATTERNS = {
    "cache",
    "cached",
    "cache_result",
    "cache_key",
    "redis_cache",
    "memcached",
    "ttl",
}

_STORAGE_PATTERNS = {
    "s3": {"s3", "aws_s3", "s3_storage", "object_store"},
    "redis": {"redis", "redis_cache", "redis_store"},
    "blob": {"blob", "blob_storage", "azure_blob"},
    "gcs": {"gcs", "google_cloud_storage", "gcs_storage"},
    "elasticsearch": {"elasticsearch", "es", "elastic"},
    "mongodb": {"mongodb", "mongo", "mongo_db"},
}

# SQL-related file extensions
_SQL_EXTENSIONS = {".sql", ".prisma", ".graphql"}

# ORM model naming patterns
_MODEL_SUFFIXES = {
    "model",
    "models",
    "entity",
    "entities",
    "schema",
    "schema",
    "dto",
    "dao",
    "repository",
}


class DataCompilationPass(OperationalCompilerPass):
    """
    Pass 2 of Operational compilation.

    Compiles data/persistent state affected by the change.
    """

    @property
    def name(self) -> str:
        return "data_compilation"

    def validate_input(self, context: OperationalPassContext) -> bool:
        """Verify the composed model exists."""
        return context.composed_model is not None

    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Execute data analysis on the composed model.

        Args:
            context: Pass context with composed_model set.

        Returns:
            Updated context with data model set on composed_model.
        """
        if not self.validate_input(context):
            return context

        model = context.composed_model
        if model is None:
            return context

        # Use cached values from context
        affected_symbol_ids = context.get_affected_symbol_ids()
        symbol_map = context.get_symbol_map()
        reachable_ids = context.get_reachable_ids()

        # Combine affected + reachable for data analysis
        all_relevant_ids = affected_symbol_ids | reachable_ids

        # Classify relevant symbols into data categories
        models: list[Symbol] = []
        reads: list[Symbol] = []
        writes: list[Symbol] = []
        transactions: list[Symbol] = []
        tables: set[str] = set()
        caches: set[str] = set()
        external_storage: list[tuple[str, str]] = []

        for sid in all_relevant_ids:
            sym = symbol_map.get(sid)
            if sym is None:
                continue

            # Check for data model classes
            if self._is_data_model(sym):
                models.append(sym)

            # Check for read operations
            if self._is_read_operation(sym):
                reads.append(sym)

            # Check for write operations
            if self._is_write_operation(sym):
                writes.append(sym)

            # Check for transactional boundaries
            if self._is_transactional(sym):
                transactions.append(sym)

            # Extract table names from properties
            table_name = self._extract_table_name(sym)
            if table_name:
                tables.add(table_name)

            # Extract cache references
            cache_ref = self._extract_cache_reference(sym)
            if cache_ref:
                caches.add(cache_ref)

            # Extract external storage references
            storage_refs = self._extract_storage_references(sym)
            external_storage.extend(storage_refs)

        # Also check SQL files in affected files
        affected_files: set[str] = set()
        for sid in affected_symbol_ids:
            if sid in symbol_map:
                affected_files.add(symbol_map[sid].file)
        for file_path in affected_files:
            if any(file_path.endswith(ext) for ext in _SQL_EXTENSIONS):
                # Infer table name from SQL file name
                table_name = file_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                tables.add(table_name)

        data_model = DataModel(
            models=tuple(sorted(models, key=lambda s: s.id)),
            tables=tuple(sorted(tables)),
            reads=tuple(sorted(reads, key=lambda s: s.id)),
            writes=tuple(sorted(writes, key=lambda s: s.id)),
            transactions=tuple(sorted(transactions, key=lambda s: s.id)),
            caches=tuple(sorted(caches)),
            external_storage=tuple(sorted(external_storage)),
        )

        # Enrich the composed model
        context.composed_model = model.__class__(
            repository=model.repository,
            change=model.change,
            behavior=model.behavior,
            dependency=model.dependency,
            data=data_model,
            event=model.event,
            validation=model.validation,
            api=model.api if hasattr(model, "api") else None,
            metrics=model.metrics if hasattr(model, "metrics") else None,
        )

        return context

    @staticmethod
    def _compute_reachable_ids(
        repo: RepositoryModel,
        seed_ids: set[str],
    ) -> set[str]:
        """
        Compute all symbol IDs reachable from seed IDs via the call graph.

        Uses BFS to traverse the call graph outward from seed symbols.
        """
        # Build adjacency: caller -> list of callees
        from collections import deque

        adj: dict[str, list[str]] = defaultdict(list)
        if hasattr(repo, "call_graph") and repo.call_graph is not None:
            for edge in repo.call_graph.edges:
                adj[edge.caller_id].append(edge.callee_id)

        reachable: set[str] = set()
        queue: deque[str] = deque(seed_ids)

        while queue:
            current = queue.popleft()
            if current in reachable:
                continue
            reachable.add(current)
            if hasattr(repo, "get_callees") and not (
                hasattr(repo, "call_graph") and repo.call_graph is not None
            ):
                for call in repo.get_callees(current):
                    if call.callee_id not in reachable:
                        queue.append(call.callee_id)
            else:
                for neighbor in adj.get(current, []):
                    if neighbor not in reachable:
                        queue.append(neighbor)

        return reachable - seed_ids

    @staticmethod
    def _is_data_model(sym: Symbol) -> bool:
        """Check if a symbol represents a data model."""
        if sym.kind in (SymbolKind.CLASS, SymbolKind.INTERFACE):
            name_lower = sym.name.lower()
            # Check naming conventions
            if any(name_lower.endswith(suffix) for suffix in _MODEL_SUFFIXES):
                return True
            # Check properties for ORM annotations
            props = sym.properties
            if props.get("decorators"):
                decorators = props["decorators"]
                if isinstance(decorators, (list, tuple)):
                    deco_str = " ".join(str(d).lower() for d in decorators)
                    if any(
                        p in deco_str for p in ("model", "entity", "table", "document")
                    ):
                        return True
            # Check for database-related properties
            if any(
                k in props for k in ("table", "collection", "tablename", "table_name")
            ):
                return True
        return False

    @staticmethod
    def _is_read_operation(sym: Symbol) -> bool:
        """Check if a symbol represents a read operation."""
        name_lower = sym.name.lower()
        if any(pattern in name_lower for pattern in _READ_PATTERNS):
            return True
        # Check properties for query annotations
        props = sym.properties
        if props.get("decorators"):
            decorators = props["decorators"]
            if isinstance(decorators, (list, tuple)):
                deco_str = " ".join(str(d).lower() for d in decorators)
                if any(p in deco_str for p in ("select", "query", "get", "read")):
                    return True
        return False

    @staticmethod
    def _is_write_operation(sym: Symbol) -> bool:
        """Check if a symbol represents a write operation."""
        name_lower = sym.name.lower()
        if any(pattern in name_lower for pattern in _WRITE_PATTERNS):
            return True
        # Check properties for mutation annotations
        props = sym.properties
        if props.get("decorators"):
            decorators = props["decorators"]
            if isinstance(decorators, (list, tuple)):
                deco_str = " ".join(str(d).lower() for d in decorators)
                if any(
                    p in deco_str
                    for p in ("insert", "update", "delete", "save", "write")
                ):
                    return True
        return False

    @staticmethod
    def _is_transactional(sym: Symbol) -> bool:
        """Check if a symbol represents a transactional boundary."""
        name_lower = sym.name.lower()
        if any(pattern in name_lower for pattern in _TRANSACTION_PATTERNS):
            return True
        # Check properties for transaction annotations
        props = sym.properties
        if props.get("decorators"):
            decorators = props["decorators"]
            if isinstance(decorators, (list, tuple)):
                deco_str = " ".join(str(d).lower() for d in decorators)
                if any(p in deco_str for p in _TRANSACTION_PATTERNS):
                    return True
        return False

    @staticmethod
    def _extract_table_name(sym: Symbol) -> str | None:
        """Extract a database table name from a symbol's properties."""
        props = sym.properties
        # Check explicit table name properties
        for key in ("table", "collection", "tablename", "table_name", "from_table"):
            if key in props:
                return str(props[key])
        # Infer from class name (snake_case)
        if sym.kind in (SymbolKind.CLASS, SymbolKind.INTERFACE):
            # Convert CamelCase to snake_case as a convention
            name = sym.name
            import re

            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
            # Common pluralization
            if not snake.endswith("s"):
                snake = snake + "s"
            return snake
        return None

    @staticmethod
    def _extract_cache_reference(sym: Symbol) -> str | None:
        """Extract a cache reference from a symbol's properties."""
        name_lower = sym.name.lower()
        if any(pattern in name_lower for pattern in _CACHE_PATTERNS):
            return sym.name
        props = sym.properties
        if props.get("decorators"):
            decorators = props["decorators"]
            if isinstance(decorators, (list, tuple)):
                for d in decorators:
                    d_str = str(d).lower()
                    for pattern in _CACHE_PATTERNS:
                        if pattern in d_str:
                            return str(d)
        return None

    @staticmethod
    def _extract_storage_references(sym: Symbol) -> list[tuple[str, str]]:
        """Extract external storage references from a symbol."""
        refs: list[tuple[str, str]] = []
        name_lower = sym.name.lower()
        props = sym.properties

        # Check name for storage patterns
        for storage_type, patterns in _STORAGE_PATTERNS.items():
            if any(p in name_lower for p in patterns):
                refs.append((storage_type, sym.name))

        # Check properties
        for key, value in props.items():
            key_lower = key.lower()
            val_str = str(value).lower()
            for storage_type, patterns in _STORAGE_PATTERNS.items():
                if any(p in key_lower or p in val_str for p in patterns):
                    refs.append((storage_type, f"{key}={value}"))

        return refs
