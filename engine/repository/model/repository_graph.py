"""Repository graph - the patchable, long-lived representation of a code repository."""

import pickle
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
    type_relationship_graph: TypeRelationshipGraph = field(default_factory=lambda: TypeRelationshipGraph())
    entry_points: tuple[EntryPoint, ...] = field(default_factory=tuple)
    async_entry_points: tuple[AsyncEntryPoint, ...] = field(default_factory=tuple)
    persistence_models: tuple[PersistenceModel, ...] = field(default_factory=tuple)
    repository_methods: tuple[RepositoryMethod, ...] = field(default_factory=tuple)
    event_constructs: tuple[EventConstruct, ...] = field(default_factory=tuple)
    test_definitions: tuple[TestDefinition, ...] = field(default_factory=tuple)
    configuration_references: tuple[ConfigurationReference, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Reverse dependency indexes for O(1) incremental compilation lookup
    symbol_to_callers: dict[str, set[str]] = field(default_factory=dict)
    symbol_to_importers: dict[str, set[str]] = field(default_factory=dict)
    unresolved_symbol_to_waiting_files: dict[str, set[str]] = field(default_factory=dict)

    # Per-file edge and construct buckets for fine-grained edge-level updates
    file_to_call_edges: dict[str, list[Any]] = field(default_factory=dict)
    file_to_reference_edges: dict[str, list[Any]] = field(default_factory=dict)
    file_to_type_edges: dict[str, list[Any]] = field(default_factory=dict)
    file_to_entry_points: dict[str, list[Any]] = field(default_factory=dict)
    file_to_async_entry_points: dict[str, list[Any]] = field(default_factory=dict)
    file_to_persistence: dict[str, list[Any]] = field(default_factory=dict)
    file_to_methods: dict[str, list[Any]] = field(default_factory=dict)
    file_to_events: dict[str, list[Any]] = field(default_factory=dict)
    file_to_tests: dict[str, list[Any]] = field(default_factory=dict)
    file_to_configs: dict[str, list[Any]] = field(default_factory=dict)

    def to_model(self) -> RepositoryModel:
        """Convert to the immutable RepositoryModel expected by downstream compilers."""
        import time
        from core.logging import pipeline_logger
        start = time.perf_counter()
        pipeline_logger.log_pipeline(
            f"[to_model] Converting RepositoryGraph → RepositoryModel ({len(self.files)} files, {len(self.symbols)} symbols, {len(self.imports)} imports)...",
            to_terminal=True,
        )
        pipeline_logger.log_pipeline("[to_model] Building symbol list...", to_terminal=True)
        all_symbols = frozenset(self.symbols.values()) | frozenset(self.imports.values())
        pipeline_logger.log_pipeline("[to_model] Constructing RepositoryModel...", to_terminal=True)
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
        pipeline_logger.log_pipeline(f"[to_model] Done ({elapsed:.3f}s)", to_terminal=True)
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
        self.unresolved_symbol_to_waiting_files.clear()
        for f_path, contrib in self.files.items():
            for call in contrib.calls:
                if call.callee:
                    self.unresolved_symbol_to_waiting_files.setdefault(call.callee, set()).add(f_path)
            for ref in contrib.references:
                if ref.name:
                    self.unresolved_symbol_to_waiting_files.setdefault(ref.name, set()).add(f_path)

    def rebuild_reverse_indexes(self) -> None:
        """Rebuild all reverse dependency indexes and per-file edge buckets from current graphs."""
        self.symbol_to_callers.clear()
        self.symbol_to_importers.clear()
        self.file_to_call_edges.clear()
        self.file_to_reference_edges.clear()
        self.file_to_type_edges.clear()
        self.file_to_entry_points.clear()
        self.file_to_async_entry_points.clear()
        self.file_to_persistence.clear()
        self.file_to_methods.clear()
        self.file_to_events.clear()
        self.file_to_tests.clear()
        self.file_to_configs.clear()

        # Build unresolved symbol waiting map from file contributions
        self.rebuild_unresolved_waiting_files()

        # Build symbol_to_callers and file_to_call_edges
        for edge in self.call_graph.edges:
            caller_file = edge.file
            if not caller_file and "://" in edge.caller_id:
                caller_file = edge.caller_id.split("://")[1].split("::")[0].split("#")[0]
            if caller_file:
                self.file_to_call_edges.setdefault(caller_file, []).append(edge)
            self.symbol_to_callers.setdefault(edge.callee_id, set()).add(caller_file)

        # Build symbol_to_importers and file_to_reference_edges
        for ref_edge in self.reference_graph.edges:
            src_file = ""
            if "://" in ref_edge.source_id:
                src_file = ref_edge.source_id.split("://")[1].split("::")[0].split("#")[0]
            if src_file:
                self.file_to_reference_edges.setdefault(src_file, []).append(ref_edge)
            self.symbol_to_importers.setdefault(ref_edge.target_id, set()).add(src_file)

        # Build per-file type edges
        for t_edge in self.type_relationship_graph.edges:
            src_file = ""
            if hasattr(t_edge, "evidence") and t_edge.evidence and t_edge.evidence.file_location:
                src_file = str(t_edge.evidence.file_location.file)
            elif "://" in t_edge.source_id:
                src_file = t_edge.source_id.split("://")[1].split("::")[0].split("#")[0]
            if src_file:
                self.file_to_type_edges.setdefault(src_file, []).append(t_edge)

        # Helper to index constructs by file
        def _get_file(item: Any) -> str:
            if hasattr(item, "file") and item.file:
                return str(item.file)
            if hasattr(item, "evidence") and item.evidence and item.evidence.file_location:
                return str(item.evidence.file_location.file)
            if hasattr(item, "handler_id") and "://" in str(item.handler_id):
                return str(item.handler_id).split("://")[1].split("::")[0].split("#")[0]
            if hasattr(item, "symbol_id") and "://" in str(item.symbol_id):
                return str(item.symbol_id).split("://")[1].split("::")[0].split("#")[0]
            return ""

        for ep in self.entry_points:
            f = _get_file(ep)
            if f: self.file_to_entry_points.setdefault(f, []).append(ep)
        for aep in self.async_entry_points:
            f = _get_file(aep)
            if f: self.file_to_async_entry_points.setdefault(f, []).append(aep)
        for pm in self.persistence_models:
            f = _get_file(pm)
            if f: self.file_to_persistence.setdefault(f, []).append(pm)
        for rm in self.repository_methods:
            f = _get_file(rm)
            if f: self.file_to_methods.setdefault(f, []).append(rm)
        for ev in self.event_constructs:
            f = _get_file(ev)
            if f: self.file_to_events.setdefault(f, []).append(ev)
        for td in self.test_definitions:
            f = _get_file(td)
            if f: self.file_to_tests.setdefault(f, []).append(td)
        for cr in self.configuration_references:
            f = _get_file(cr)
            if f: self.file_to_configs.setdefault(f, []).append(cr)
