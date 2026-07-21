"""LLMContext model — lossless compressed IR optimized for LLM consumption.

Every dataclass is frozen (immutable). The model is designed for:
    - Lossless round-trip back to ReviewContext
    - Minimal token consumption via enum encoding, string tables, and compact arrays
    - Deterministic ordering
    - No semantic interpretation or information loss

Compression strategies:
    1. Enum encoding: repeated enum strings (kind, visibility, language, etc.) use integer IDs
    2. String table: all other repeated strings stored once with integer indices
    3. URI decomposition: fully-qualified URIs broken into file+symbol references
    4. Source location normalization: "file.py:1-10" → (file_id, [start, end])
    5. Remove duplicate labels: symbol names derivable from IDs are not stored
    6. Compact arrays: positional tuples instead of verbose objects
    7. Short keys: 1-3 character field names throughout
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Enum Tables — integer-encoded repeated enum values
# ---------------------------------------------------------------------------

# Each enum maps an integer ID to its string value.
# The LLM can reconstruct the original strings from these tables.
# Index 0 is always reserved for empty string in each enum.

ENUM_KIND = {
    0: "",
    1: "class",
    2: "function",
    3: "method",
    4: "import",
    5: "variable",
    6: "endpoint",
    7: "worker",
    8: "task",
    9: "route",
    10: "property",
    11: "attribute",
    12: "parameter",
    13: "module",
    14: "package",
    15: "interface",
    16: "enum",
    17: "constant",
    18: "type_alias",
    19: "decorator",
    20: "exception",
}

ENUM_VIS = {
    0: "",
    1: "public",
    2: "private",
    3: "protected",
    4: "internal",
}

ENUM_LANG = {
    0: "",
    1: "python",
    2: "java",
    3: "typescript",
    4: "javascript",
    5: "go",
    6: "rust",
    7: "kotlin",
    8: "ruby",
    9: "csharp",
    10: "cpp",
    11: "sql",
    12: "yaml",
    13: "json",
    14: "xml",
    15: "dockerfile",
    16: "shell",
    17: "terraform",
    18: "graphql",
}

ENUM_CT = {
    0: "",
    1: "modified",
    2: "added",
    3: "removed",
    4: "mixed",
    5: "renamed",
    6: "copied",
}

ENUM_REF_KIND = {
    0: "",
    1: "behavior",
    2: "change",
    3: "symbol",
    4: "file",
    5: "endpoint",
    6: "dependency",
    7: "import",
    8: "call",
    9: "reference",
    10: "implementation",
    11: "inheritance",
    12: "composition",
}

ENUM_BH_KIND = {
    0: "",
    1: "deep_execution",
    2: "shared_execution",
    3: "boundary_crossing",
    4: "event_publication",
    5: "hidden_relationship",
    6: "public_interface_change",
    7: "shared_dependency",
    8: "state_mutation",
    9: "validation_gap",
    10: "entry_point",
    11: "terminal_point",
    12: "reachable_unit",
    13: "execution_chain",
}

ENUM_METHOD = {
    0: "",
    1: "POST",
    2: "GET",
    3: "PUT",
    4: "DELETE",
    5: "PATCH",
    6: "HEAD",
    7: "OPTIONS",
    8: "worker",
    9: "event",
    10: "cron",
    11: "webhook",
}

ENUM_CLS = {
    0: "",
    1: "modification",
    2: "addition",
    3: "removal",
    4: "refactor",
    5: "fix",
    6: "feature",
    7: "mixed",
}

ENUM_SCOPE = {
    0: "",
    1: "local",
    2: "multi_file",
    3: "cross_package",
    4: "cross_service",
    5: "global",
}

ENUM_BH_CHANGE = {
    0: "",
    1: "FunctionBodyChange",
    2: "SignatureChange",
    3: "ClassBodyChange",
    4: "InterfaceChange",
    5: "ImportChange",
    6: "DecoratorChange",
    7: "TypeAnnotationChange",
    8: "DocstringChange",
    9: "VisibilityChange",
    10: "AsyncChange",
    11: "ExceptionChange",
    12: "DependencyChange",
    13: "ConfigurationChange",
    14: "RouteChange",
    15: "SchemaChange",
    16: "MigrationChange",
    17: "TestChange",
    18: "ReturnTypeChange",
    19: "ParameterChange",
    20: "AccessModifierChange",
}

# All enum tables indexed by name for easy lookup
ENUM_TABLES: dict[str, dict[int, str]] = {
    "kind": ENUM_KIND,
    "vis": ENUM_VIS,
    "lang": ENUM_LANG,
    "ct": ENUM_CT,
    "ref_kind": ENUM_REF_KIND,
    "bh_kind": ENUM_BH_KIND,
    "method": ENUM_METHOD,
    "cls": ENUM_CLS,
    "scope": ENUM_SCOPE,
    "bh_change": ENUM_BH_CHANGE,
}

# Reverse mappings: string -> int for each enum
ENUM_REVERSE: dict[str, dict[str, int]] = {
    name: {v: k for k, v in table.items()}
    for name, table in ENUM_TABLES.items()
}


# ---------------------------------------------------------------------------
# String Table — global string dictionary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StringTable:
    """Global string dictionary.

    Every repeated string is stored once in this table.
    All other entries reference strings by their positional index.
    Index 0 is reserved for the empty string.
    """
    entries: tuple[str, ...] = field(default_factory=tuple)

    def __getitem__(self, idx: int) -> str:
        return self.entries[idx]

    def __len__(self) -> int:
        return len(self.entries)


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
    # Each node: (bh_idx, sym_idx, kind_id, depth, changed, shared,
    #             reaches_svc_idx, reaches_mod_idx, reaches_pkg_idx,
    #             (ref_idxs...))

    edges: tuple[tuple[int, int], ...] = field(default_factory=tuple)
    # Each edge: (parent_node_idx, child_node_idx)


# ---------------------------------------------------------------------------
# LLMContext — the compressed IR
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMContext:
    """Lossless compressed IR optimized for LLM consumption.

    Contains every fact from ReviewContext but eliminates representational
    redundancy through:
        - Enum encoding for repeated categorical values
        - Global string dictionary (StringTable) for other repeated strings
        - URI decomposition into file+symbol references
        - Source location normalization: (file_id, [start, end])
        - Removal of duplicate human labels derivable from IDs
        - Compact positional arrays instead of verbose objects
        - DAG representation for execution chains
        - Short (1-3 char) field names

    This is fully reversible back to an equivalent ReviewContext.
    No semantic interpretation, no information loss.
    """

    # -----------------------------------------------------------------------
    # String Dictionary
    # -----------------------------------------------------------------------
    st: StringTable = field(default_factory=StringTable)

    # -----------------------------------------------------------------------
    # Normalized Lookup Tables
    # -----------------------------------------------------------------------

    # Files: (path_idx, lang_id, ct_id)
    f: tuple[tuple[int, int, int], ...] = field(default_factory=tuple)

    # Symbols: (file_id, name_idx, kind_id, vis_id, (start_line, end_line))
    # name_idx can be 0 if name is derivable from the symbol id
    # location is normalized to (start_line, end_line) instead of "file.py:1-10"
    sym: tuple[tuple[int, int, int, int, tuple[int, int]], ...] = field(default_factory=tuple)

    # Behaviors: (sym_id, kind_id)
    # References existing symbol instead of duplicating name/URI
    bh: tuple[tuple[int, int], ...] = field(default_factory=tuple)

    # References: (id_idx, kind_id, location_idx, artifact_idx)
    ref: tuple[tuple[int, int, int, int], ...] = field(default_factory=tuple)

    # Endpoints: (endpoint_idx, method_id, path_idx)
    ep: tuple[tuple[int, int, int], ...] = field(default_factory=tuple)

    # -----------------------------------------------------------------------
    # Change Section
    # -----------------------------------------------------------------------

    # Summary: (cls_id, scope_id, file_count, sym_count, bh_count)
    cs: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)

    # File changes: (file_idx, ((sym_idx, ct_id, (bh_change_ids...)), ...))
    cf: tuple[tuple, ...] = field(default_factory=tuple)

    # -----------------------------------------------------------------------
    # Execution Section
    # -----------------------------------------------------------------------

    # Execution DAG
    eg: ExecutionGraph = field(default_factory=ExecutionGraph)

    # Entry points: (ep_idx, (node_idxs...), terminal_idx, max_depth)
    epts: tuple[tuple, ...] = field(default_factory=tuple)

    # Deepest execution: (ep_idx, depth)
    de: tuple[int, int] = (0, 0)

    # -----------------------------------------------------------------------
    # Discoveries Section
    # -----------------------------------------------------------------------

    # Discoveries: (id_idx, kind_id, facts, (ref_idxs...))
    disc: tuple[tuple, ...] = field(default_factory=tuple)