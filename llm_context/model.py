"""LLMContext model — token-efficient representation of ReviewContext.

Every dataclass is frozen (immutable). The model is designed for:
    - Lossless round-trip back to ReviewContext
    - Minimal token consumption via normalized tables and positional arrays
    - Deterministic ordering
    - No semantic interpretation or information loss
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# String Table — global string dictionary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StringTable:
    """Global string dictionary.

    Every repeated string is stored once in this table.
    All other entries reference strings by their positional index.
    """
    entries: tuple[str, ...] = field(default_factory=tuple)

    def __getitem__(self, idx: int) -> str:
        return self.entries[idx]

    def __len__(self) -> int:
        return len(self.entries)


# ---------------------------------------------------------------------------
# Normalized Lookup Tables
# ---------------------------------------------------------------------------

# Each entry stores indices into the StringTable for its fields.
# Using positional tuples eliminates repeated field names.

# FileEntry: (path_idx, language_idx, change_type_idx)
# SymbolEntry: (id_idx, name_idx, kind_idx, visibility_idx, language_idx, location_idx)
# BehaviorEntry: (id_idx, name_idx, kind_idx)
# ReferenceEntry: (id_idx, kind_idx, location_idx, compiler_artifact_idx)
# EndpointEntry: (endpoint_idx, method_idx, path_idx)

# These are stored as tuples of tuples in LLMContext directly.
# No wrapper dataclasses needed — the positional tuples ARE the schema.


# ---------------------------------------------------------------------------
# Execution DAG
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionGraph:
    """Directed acyclic graph of execution steps.

    Nodes represent individual execution steps.
    Edges represent parent→child relationships (execution flow).

    This eliminates duplicate execution chains by factoring shared prefixes
    into a single DAG structure.
    """
    nodes: tuple[tuple, ...] = field(default_factory=tuple)
    # Each node: (behavior_idx, symbol_idx, kind_idx, depth, changed, shared,
    #             reaches_service_idx, reaches_module_idx, reaches_package_idx,
    #             (ref_idxs...))

    edges: tuple[tuple[int, int], ...] = field(default_factory=tuple)
    # Each edge: (parent_node_idx, child_node_idx)


# ---------------------------------------------------------------------------
# LLMContext — the token-efficient representation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMContext:
    """Token-efficient, lossless representation of ReviewContext.

    Contains every fact from ReviewContext but eliminates representational
    redundancy through:
        - Global string dictionary (StringTable)
        - Normalized lookup tables for repeated objects
        - Positional arrays instead of repeated field names
        - DAG representation for execution chains
        - Canonical IDs (F1, S1, B1, R1, E1) for all reusable entities

    This is fully reversible back to an equivalent ReviewContext.
    No semantic interpretation, no information loss.
    """

    # -----------------------------------------------------------------------
    # String Dictionary
    # -----------------------------------------------------------------------
    strings: StringTable = field(default_factory=StringTable)

    # -----------------------------------------------------------------------
    # Normalized Lookup Tables
    # -----------------------------------------------------------------------

    # Files: tuple of (path_idx, language_idx, change_type_idx)
    files: tuple[tuple[int, int, int], ...] = field(default_factory=tuple)

    # Symbols: tuple of (id_idx, name_idx, kind_idx, visibility_idx, language_idx, location_idx)
    symbols: tuple[tuple[int, int, int, int, int, int], ...] = field(default_factory=tuple)

    # Behaviors: tuple of (id_idx, name_idx, kind_idx)
    behaviors: tuple[tuple[int, int, int], ...] = field(default_factory=tuple)

    # References: tuple of (id_idx, kind_idx, location_idx, compiler_artifact_idx)
    references: tuple[tuple[int, int, int, int], ...] = field(default_factory=tuple)

    # Endpoints: tuple of (endpoint_idx, method_idx, path_idx)
    endpoints: tuple[tuple[int, int, int], ...] = field(default_factory=tuple)

    # -----------------------------------------------------------------------
    # Change Section
    # -----------------------------------------------------------------------

    # Summary: (classification_idx, scope_idx, file_count, symbol_count, behavior_count)
    change_summary: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)

    # File changes: tuple of (file_idx, ((symbol_idx, change_type_idx, (behavior_change_idxs...)), ...))
    change_files: tuple[tuple, ...] = field(default_factory=tuple)

    # -----------------------------------------------------------------------
    # Execution Section
    # -----------------------------------------------------------------------

    # Execution DAG
    execution_graph: ExecutionGraph = field(default_factory=ExecutionGraph)

    # Entry points: tuple of (endpoint_idx, (chain_node_idxs...), terminal_idx, max_depth)
    entry_points: tuple[tuple, ...] = field(default_factory=tuple)

    # Deepest execution: (endpoint_idx, depth)
    deepest_execution: tuple[int, int] = (0, 0)

    # -----------------------------------------------------------------------
    # Discoveries Section
    # -----------------------------------------------------------------------

    # Discoveries: tuple of (id_idx, kind_idx, facts_dict, (ref_idxs...))
    discoveries: tuple[tuple, ...] = field(default_factory=tuple)