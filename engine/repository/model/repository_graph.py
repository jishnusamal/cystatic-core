"""Repository graph - the patchable, long-lived representation of a code repository."""

import pickle
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any

from .symbol import Symbol
from .graphs import CallGraph, ReferenceGraph, TypeRelationshipGraph
from .repository_model import RepositoryModel, EntryPoint, AsyncEntryPoint
from .persistence import PersistenceModel, RepositoryMethod
from .events import EventConstruct
from .tests import TestDefinition
from .configuration import ConfigurationReference
from .file_contribution import FileContribution
from core.runtime import assert_new_architecture


@dataclass
class IndexStats:
    reads: int = 0
    total_lookup_time_ns: int = 0
    max_lookup_time_ns: int = 0
    materializations: int = 0
    unique_keys: int = 0
    materialized_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        avg_ns = self.total_lookup_time_ns / self.reads if self.reads > 0 else 0
        return {
            "read_count": self.reads,
            "unique_keys": self.unique_keys,
            "total_time_ms": self.total_lookup_time_ns / 1_000_000.0,
            "avg_time_ms": avg_ns / 1_000_000.0,
            "max_time_ms": self.max_lookup_time_ns / 1_000_000.0,
            "materializations": self.materializations,
            "materialized_size_bytes": self.materialized_size,
        }


@dataclass
class DerivedIndexCache:
    symbol_to_callers: dict[str, set[str]] | None = None
    symbol_to_importers: dict[str, set[str]] | None = None
    unresolved_symbol_to_waiting_files: dict[str, set[str]] | None = None
    file_to_call_edges: dict[str, list[Any]] | None = None
    file_to_reference_edges: dict[str, list[Any]] | None = None
    file_to_type_edges: dict[str, list[Any]] | None = None
    file_to_entry_points: dict[str, list[Any]] | None = None
    file_to_async_entry_points: dict[str, list[Any]] | None = None
    file_to_persistence: dict[str, list[Any]] | None = None
    file_to_methods: dict[str, list[Any]] | None = None
    file_to_events: dict[str, list[Any]] | None = None
    file_to_tests: dict[str, list[Any]] | None = None
    file_to_configs: dict[str, list[Any]] | None = None

    def clear(self) -> None:
        self.symbol_to_callers = None
        self.symbol_to_importers = None
        self.unresolved_symbol_to_waiting_files = None
        self.file_to_call_edges = None
        self.file_to_reference_edges = None
        self.file_to_type_edges = None
        self.file_to_entry_points = None
        self.file_to_async_entry_points = None
        self.file_to_persistence = None
        self.file_to_methods = None
        self.file_to_events = None
        self.file_to_tests = None
        self.file_to_configs = None


@dataclass
class RepositoryGraph:
    """
    The patchable repository graph.

    Maintains file contributions and compiled global indexes. It serves
    as a long-lived serializable database that can be patched with diffs.
    """

    files: dict[str, FileContribution] = field(default_factory=dict)
    symbols: dict[str, Symbol] = field(default_factory=dict)
    imports: dict[str, Symbol] = field(default_factory=dict)
    call_graph: CallGraph = field(default_factory=lambda: CallGraph())
    reference_graph: ReferenceGraph = field(default_factory=lambda: ReferenceGraph())
    type_relationship_graph: TypeRelationshipGraph = field(
        default_factory=lambda: TypeRelationshipGraph()
    )
    entry_points: tuple[EntryPoint, ...] = field(default_factory=tuple)
    async_entry_points: tuple[AsyncEntryPoint, ...] = field(default_factory=tuple)
    persistence_models: tuple[PersistenceModel, ...] = field(default_factory=tuple)
    repository_methods: tuple[RepositoryMethod, ...] = field(default_factory=tuple)
    event_constructs: tuple[EventConstruct, ...] = field(default_factory=tuple)
    test_definitions: tuple[TestDefinition, ...] = field(default_factory=tuple)
    configuration_references: tuple[ConfigurationReference, ...] = field(
        default_factory=tuple
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    # In-memory only cache and stats
    _indexes: DerivedIndexCache = field(
        default_factory=DerivedIndexCache, init=False, repr=False, compare=False
    )
    _index_stats: dict[str, IndexStats] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Guard: fail loudly if created in a new-architecture-only context."""
        assert_new_architecture("RepositoryGraph")

    @contextlib.contextmanager
    def index_usage(self, index_name: str):
        stats = self._index_stats.setdefault(index_name, IndexStats())
        start = time.perf_counter_ns()
        try:
            yield stats
        finally:
            elapsed = time.perf_counter_ns() - start
            stats.reads += 1
            stats.total_lookup_time_ns += elapsed
            if elapsed > stats.max_lookup_time_ns:
                stats.max_lookup_time_ns = elapsed

    @property
    def symbol_to_callers(self) -> dict[str, set[str]]:
        if self._indexes.symbol_to_callers is None:
            self._materialize_reverse_indexes()
        return self._indexes.symbol_to_callers

    @property
    def symbol_to_importers(self) -> dict[str, set[str]]:
        if self._indexes.symbol_to_importers is None:
            self._materialize_reverse_indexes()
        return self._indexes.symbol_to_importers

    @property
    def unresolved_symbol_to_waiting_files(self) -> dict[str, set[str]]:
        if self._indexes.unresolved_symbol_to_waiting_files is None:
            self._materialize_unresolved_waiting_files()
        return self._indexes.unresolved_symbol_to_waiting_files

    @property
    def file_to_call_edges(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_call_edges is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_call_edges

    @property
    def file_to_reference_edges(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_reference_edges is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_reference_edges

    @property
    def file_to_type_edges(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_type_edges is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_type_edges

    @property
    def file_to_entry_points(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_entry_points is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_entry_points

    @property
    def file_to_async_entry_points(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_async_entry_points is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_async_entry_points

    @property
    def file_to_persistence(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_persistence is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_persistence

    @property
    def file_to_methods(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_methods is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_methods

    @property
    def file_to_events(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_events is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_events

    @property
    def file_to_tests(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_tests is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_tests

    @property
    def file_to_configs(self) -> dict[str, list[Any]]:
        if self._indexes.file_to_configs is None:
            self._materialize_reverse_indexes()
        return self._indexes.file_to_configs

    # Semantic abstraction APIs
    def callers_of(self, symbol_id: str) -> set[str]:
        with self.index_usage("symbol_to_callers") as stats:
            res = self.symbol_to_callers.get(symbol_id, set())
            stats.unique_keys = len(self.symbol_to_callers)
            return res

    def importers_of(self, symbol_id: str) -> set[str]:
        with self.index_usage("symbol_to_importers") as stats:
            res = self.symbol_to_importers.get(symbol_id, set())
            stats.unique_keys = len(self.symbol_to_importers)
            return res

    def waiting_files_for(self, symbol_name: str) -> set[str]:
        with self.index_usage("unresolved_symbol_to_waiting_files") as stats:
            res = self.unresolved_symbol_to_waiting_files.get(symbol_name, set())
            stats.unique_keys = len(self.unresolved_symbol_to_waiting_files)
            return res

    def call_edges_for_file(self, file_path: str) -> list[Any]:
        with self.index_usage("file_to_call_edges") as stats:
            res = self.file_to_call_edges.get(file_path, [])
            stats.unique_keys = len(self.file_to_call_edges)
            return res

    def reference_edges_for_file(self, file_path: str) -> list[Any]:
        with self.index_usage("file_to_reference_edges") as stats:
            res = self.file_to_reference_edges.get(file_path, [])
            stats.unique_keys = len(self.file_to_reference_edges)
            return res

    def clear_file_indexes(self, file_path: str) -> None:
        """Clear all per-file index entries for a file."""
        for name in [
            "file_to_call_edges",
            "file_to_reference_edges",
            "file_to_type_edges",
            "file_to_entry_points",
            "file_to_async_entry_points",
            "file_to_persistence",
            "file_to_methods",
            "file_to_events",
            "file_to_tests",
            "file_to_configs",
        ]:
            dct = getattr(self, name)
            dct.pop(file_path, None)

    def set_file_call_edges(self, file_path: str, edges: list[Any]) -> None:
        self.file_to_call_edges[file_path] = edges

    def set_file_reference_edges(self, file_path: str, edges: list[Any]) -> None:
        self.file_to_reference_edges[file_path] = edges

    def set_file_type_edges(self, file_path: str, edges: list[Any]) -> None:
        self.file_to_type_edges[file_path] = edges

    def set_file_entry_points(self, file_path: str, entry_points: list[Any]) -> None:
        self.file_to_entry_points[file_path] = entry_points

    def set_file_async_entry_points(
        self, file_path: str, async_entry_points: list[Any]
    ) -> None:
        self.file_to_async_entry_points[file_path] = async_entry_points

    def set_file_persistence(self, file_path: str, persistence: list[Any]) -> None:
        self.file_to_persistence[file_path] = persistence

    def set_file_methods(self, file_path: str, methods: list[Any]) -> None:
        self.file_to_methods[file_path] = methods

    def set_file_events(self, file_path: str, events: list[Any]) -> None:
        self.file_to_events[file_path] = events

    def set_file_tests(self, file_path: str, tests: list[Any]) -> None:
        self.file_to_tests[file_path] = tests

    def set_file_configs(self, file_path: str, configs: list[Any]) -> None:
        self.file_to_configs[file_path] = configs

    def invalidate_indexes(self) -> None:
        """Invalidate/clear all derived indexes in the cache."""
        self._indexes.clear()

    def invalidate_after_patch(self) -> None:
        """Hook called after patching is complete to release or manage caches."""
        self.invalidate_indexes()

    def to_model(self) -> RepositoryModel:
        """Convert to the immutable RepositoryModel expected by downstream compilers."""
        import time
        from core.logging import pipeline_logger

        start = time.perf_counter()
        pipeline_logger.log_pipeline(
            f"[to_model] Converting RepositoryGraph → RepositoryModel ({len(self.files)} files, {len(self.symbols)} symbols, {len(self.imports)} imports)...",
            to_terminal=True,
        )
        pipeline_logger.log_pipeline(
            "[to_model] Building symbol list...", to_terminal=True
        )
        all_symbols = frozenset(self.symbols.values()) | frozenset(
            self.imports.values()
        )
        pipeline_logger.log_pipeline(
            "[to_model] Constructing RepositoryModel...", to_terminal=True
        )
        model = RepositoryModel(
            symbols=all_symbols,
            call_graph=self.call_graph,
            reference_graph=self.reference_graph,
            type_relationship_graph=self.type_relationship_graph,
            entry_points=self.entry_points,
            async_entry_points=self.async_entry_points,
            persistence_models=self.persistence_models,
            repository_methods=self.repository_methods,
            event_constructs=self.event_constructs,
            test_definitions=self.test_definitions,
            configuration_references=self.configuration_references,
            metadata=self.metadata,
        )
        elapsed = time.perf_counter() - start
        pipeline_logger.log_pipeline(
            f"[to_model] Done ({elapsed:.3f}s)", to_terminal=True
        )
        return model

    def to_bytes(self) -> bytes:
        """Serialize the RepositoryGraph using pickle."""
        return pickle.dumps(self)

    @classmethod
    def from_bytes(cls, data: bytes) -> "RepositoryGraph":
        """Deserialize the RepositoryGraph using pickle."""
        from typing import cast

        return cast("RepositoryGraph", pickle.loads(data))

    def save_to_file(self, file_path: str) -> None:
        """Save the RepositoryGraph to a file on disk."""
        with open(file_path, "wb") as f:
            f.write(self.to_bytes())

    @classmethod
    def load_from_file(cls, file_path: str) -> "RepositoryGraph":
        """Load the RepositoryGraph from a file on disk."""
        with open(file_path, "rb") as f:
            return cls.from_bytes(f.read())

    def rebuild_unresolved_waiting_files(self) -> None:
        """Rebuild the mapping from symbol names to files waiting for/referencing them."""
        cache = self._indexes
        cache.unresolved_symbol_to_waiting_files = None
        self._materialize_unresolved_waiting_files()

    def _materialize_unresolved_waiting_files(self) -> None:
        cache = self._indexes
        if cache.unresolved_symbol_to_waiting_files is not None:
            return

        stats = self._index_stats.setdefault(
            "unresolved_symbol_to_waiting_files", IndexStats()
        )
        stats.materializations += 1

        cache.unresolved_symbol_to_waiting_files = {}
        for f_path, contrib in self.files.items():
            for call in contrib.calls:
                if call.callee:
                    cache.unresolved_symbol_to_waiting_files.setdefault(
                        call.callee, set()
                    ).add(f_path)
            for ref in contrib.references:
                if ref.name:
                    cache.unresolved_symbol_to_waiting_files.setdefault(
                        ref.name, set()
                    ).add(f_path)

        from benchmark.size_estimator import get_retained_size

        stats.unique_keys = len(cache.unresolved_symbol_to_waiting_files)
        stats.materialized_size = get_retained_size(
            cache.unresolved_symbol_to_waiting_files
        )

    def rebuild_reverse_indexes(self) -> None:
        """Rebuild all reverse dependency indexes and per-file edge buckets from current graphs."""
        self.invalidate_indexes()
        self._materialize_reverse_indexes()

    def _materialize_reverse_indexes(self) -> None:
        cache = self._indexes
        if cache.symbol_to_callers is not None:
            return  # already materialized

        # Record materializations
        for name in [
            "symbol_to_callers",
            "symbol_to_importers",
            "file_to_call_edges",
            "file_to_reference_edges",
            "file_to_type_edges",
            "file_to_entry_points",
            "file_to_async_entry_points",
            "file_to_persistence",
            "file_to_methods",
            "file_to_events",
            "file_to_tests",
            "file_to_configs",
        ]:
            stats = self._index_stats.setdefault(name, IndexStats())
            stats.materializations += 1

        cache.symbol_to_callers = {}
        cache.symbol_to_importers = {}
        cache.file_to_call_edges = {}
        cache.file_to_reference_edges = {}
        cache.file_to_type_edges = {}
        cache.file_to_entry_points = {}
        cache.file_to_async_entry_points = {}
        cache.file_to_persistence = {}
        cache.file_to_methods = {}
        cache.file_to_events = {}
        cache.file_to_tests = {}
        cache.file_to_configs = {}

        # Rebuild unresolved symbol waiting map from file contributions
        self._materialize_unresolved_waiting_files()

        # Build symbol_to_callers and file_to_call_edges
        for edge in self.call_graph.edges:
            caller_file = edge.file
            if not caller_file and "://" in edge.caller_id:
                caller_file = (
                    edge.caller_id.split("://")[1].split("::")[0].split("#")[0]
                )
            if caller_file:
                cache.file_to_call_edges.setdefault(caller_file, []).append(edge)
            cache.symbol_to_callers.setdefault(edge.callee_id, set()).add(caller_file)

        # Build symbol_to_importers and file_to_reference_edges
        for ref_edge in self.reference_graph.edges:
            src_file = ""
            if "://" in ref_edge.source_id:
                src_file = (
                    ref_edge.source_id.split("://")[1].split("::")[0].split("#")[0]
                )
            if src_file:
                cache.file_to_reference_edges.setdefault(src_file, []).append(ref_edge)
            cache.symbol_to_importers.setdefault(ref_edge.target_id, set()).add(
                src_file
            )

        # Build per-file type edges
        for t_edge in self.type_relationship_graph.edges:
            src_file = ""
            if (
                hasattr(t_edge, "evidence")
                and t_edge.evidence
                and t_edge.evidence.file_location
            ):
                src_file = str(t_edge.evidence.file_location.file)
            elif "://" in t_edge.source_id:
                src_file = t_edge.source_id.split("://")[1].split("::")[0].split("#")[0]
            if src_file:
                cache.file_to_type_edges.setdefault(src_file, []).append(t_edge)

        # Helper to index constructs by file
        def _get_file(item: Any) -> str:
            if hasattr(item, "file") and item.file:
                return str(item.file)
            if (
                hasattr(item, "evidence")
                and item.evidence
                and item.evidence.file_location
            ):
                return str(item.evidence.file_location.file)
            if hasattr(item, "handler_id") and "://" in str(item.handler_id):
                return str(item.handler_id).split("://")[1].split("::")[0].split("#")[0]
            if hasattr(item, "symbol_id") and "://" in str(item.symbol_id):
                return str(item.symbol_id).split("://")[1].split("::")[0].split("#")[0]
            return ""

        for ep in self.entry_points:
            f = _get_file(ep)
            if f:
                cache.file_to_entry_points.setdefault(f, []).append(ep)
        for aep in self.async_entry_points:
            f = _get_file(aep)
            if f:
                cache.file_to_async_entry_points.setdefault(f, []).append(aep)
        for pm in self.persistence_models:
            f = _get_file(pm)
            if f:
                cache.file_to_persistence.setdefault(f, []).append(pm)
        for rm in self.repository_methods:
            f = _get_file(rm)
            if f:
                cache.file_to_methods.setdefault(f, []).append(rm)
        for ev in self.event_constructs:
            f = _get_file(ev)
            if f:
                cache.file_to_events.setdefault(f, []).append(ev)
        for td in self.test_definitions:
            f = _get_file(td)
            if f:
                cache.file_to_tests.setdefault(f, []).append(td)
        for cr in self.configuration_references:
            f = _get_file(cr)
            if f:
                cache.file_to_configs.setdefault(f, []).append(cr)

        # Set stats sizes
        from benchmark.size_estimator import get_retained_size

        for name in [
            "symbol_to_callers",
            "symbol_to_importers",
            "file_to_call_edges",
            "file_to_reference_edges",
            "file_to_type_edges",
            "file_to_entry_points",
            "file_to_async_entry_points",
            "file_to_persistence",
            "file_to_methods",
            "file_to_events",
            "file_to_tests",
            "file_to_configs",
        ]:
            val = getattr(cache, name)
            stats = self._index_stats[name]
            stats.unique_keys = len(val)
            stats.materialized_size = get_retained_size(val)

    def index_memory_report(self) -> dict[str, Any]:
        """Return a memory size breakdown report for the indexes."""
        from benchmark.size_estimator import get_retained_size

        cache = self._indexes
        return {
            "CallGraph": {
                "edges": get_retained_size(self.call_graph.edges),
                "outgoing": get_retained_size(self.call_graph.outgoing),
                "incoming": get_retained_size(self.call_graph.incoming),
            },
            "ReferenceGraph": {
                "edges": get_retained_size(self.reference_graph.edges),
                "outgoing": get_retained_size(self.reference_graph.outgoing),
                "incoming": get_retained_size(self.reference_graph.incoming),
            },
            "TypeRelationshipGraph": {
                "edges": get_retained_size(self.type_relationship_graph.edges),
                "outgoing": get_retained_size(self.type_relationship_graph.outgoing),
                "incoming": get_retained_size(self.type_relationship_graph.incoming),
            },
            "RepositoryGraph_indexes": {
                "callers": get_retained_size(cache.symbol_to_callers)
                if cache.symbol_to_callers is not None
                else 0,
                "importers": get_retained_size(cache.symbol_to_importers)
                if cache.symbol_to_importers is not None
                else 0,
                "unresolved": get_retained_size(
                    cache.unresolved_symbol_to_waiting_files
                )
                if cache.unresolved_symbol_to_waiting_files is not None
                else 0,
                "file_calls": get_retained_size(cache.file_to_call_edges)
                if cache.file_to_call_edges is not None
                else 0,
                "file_refs": get_retained_size(cache.file_to_reference_edges)
                if cache.file_to_reference_edges is not None
                else 0,
                "file_types": get_retained_size(cache.file_to_type_edges)
                if cache.file_to_type_edges is not None
                else 0,
            },
        }

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        # Create a fresh empty cache
        state["_indexes"] = DerivedIndexCache()
        # Do not serialize stats
        state["_index_stats"] = {}
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        for k, v in state.items():
            setattr(self, k, v)
