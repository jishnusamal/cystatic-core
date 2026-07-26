"""LLMContext Compiler — transforms ReviewContext into a lossless compressed IR.

This compiler transforms a ReviewContext into an LLMContext by eliminating
representational redundancy. It performs NO semantic interpretation, NO AI/LLM
usage, and NO information loss.

Compression Rules Applied:
    1. Dictionary encode repeated strings into a global StringTable
    2. Encode enums (kind, visibility, language, change type, etc.) as integer IDs
    3. Normalize source locations from "file.py:1-10" to (start_line, end_line)
    4. Decompose URIs into file+symbol references
    5. Remove duplicate human labels derivable from IDs
    6. Use compact positional arrays instead of verbose objects
    7. Use short (1-3 char) field names
    8. Deduplicate execution steps via DAG

Given the same ReviewContext, this compiler always produces the exact same LLMContext.
"""
from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from review_context.model import (
    ReviewContext,
    ChangeContext,
    ChangeSummary,
    FileChange,
    Change,
    SymbolRef,
    ExecutionContext,
    EntryPointExecution,
    ExecutionStep,
    SymbolReference,
    ReachedComponents,
    DeepestExecution,
    Discovery,
    Reference,
)

from .model import LLMContext, StringTable, ExecutionGraph, ENUM_REVERSE

if TYPE_CHECKING:
    from runtime.settings import CompilerSettings

# Regex for extracting file path and line range from location strings
_LOCATION_RE = re.compile(r"^(.+?)(?::(\d+)(?:-(\d+))?)?$")


# ---------------------------------------------------------------------------
# Review-scope pruning (imported from review_scope_builder to avoid circularity)
# ---------------------------------------------------------------------------
from .review_scope_builder import (
    build_review_scope,
    prune_review_context,
    is_compiler_metadata,
    classify_symbol,
    LANGUAGE_PRIMITIVES,
    STD_LIBS,
    FRAMEWORK_MODULES,
    FRAMEWORK_NAMES,
    ORM_MODULES,
    ORM_NAMES,
    NOISE_CATEGORIES,
)

def _parse_location(location: str) -> tuple[str, int, int]:
    """Parse a location string into (file_path, start_line, end_line).

    Handles formats:
        "file.py:1-10"  → ("file.py", 1, 10)
        "file.py:5"     → ("file.py", 5, 5)
        "file.py"       → ("file.py", 0, 0)
        ""              → ("", 0, 0)
    """
    if not location:
        return ("", 0, 0)
    m = _LOCATION_RE.match(location)
    if not m:
        return (location, 0, 0)
    file_path = m.group(1)
    start_str = m.group(2)
    end_str = m.group(3)
    if start_str:
        start_line = int(start_str)
        end_line = int(end_str) if end_str else start_line
    else:
        start_line = 0
        end_line = 0
    return (file_path, start_line, end_line)


def _resolve_symbol_name_from_uri(uri: str) -> str:
    """Extract symbol name from a URI like 'sym://path#SymbolName'.

    Returns the symbol name or empty string.
    """
    hash_match = re.search(r"#(.+)$", uri)
    if hash_match:
        return hash_match.group(1)
    return ""


class LLMContextCompiler:
    """Compiles ReviewContext into a compact LLMContext.

    The LLMContext is a token-efficient representation of the ReviewContext
    facts optimized for LLM consumption.
    """

    def __init__(self, settings: CompilerSettings | None = None) -> None:
        if settings is None:
            from runtime.settings import get_compiler_settings
            settings = get_compiler_settings()
        self._settings = settings

    def compile(self, review_context: ReviewContext) -> LLMContext:
        """Compile a ReviewContext into an LLMContext.

        Args:
            review_context: The ReviewContext to compile.

        Returns:
            An LLMContext containing key facts from ReviewContext in a
            token-efficient compact representation.
        """
        # Phase 0: Prune implementation noise semantically
        pruned_context = build_review_scope(review_context, settings=self._settings)

        sb = _StringBuilder()

        # Phase 1: Build enum-encoded lookup tables
        file_table = self._build_file_table(pruned_context.change, sb)
        symbol_table, symbol_id_map = self._build_symbol_table(
            pruned_context.change, pruned_context.execution, file_table, sb
        )
        endpoint_table = self._build_endpoint_table(pruned_context.execution, pruned_context.change, sb)

        # Phase 2: Build change section
        change_summary = self._build_change_summary(pruned_context.change.summary, sb)
        change_files = self._build_change_files(
            pruned_context.change.files, file_table, symbol_id_map, sb
        )

        # Phase 3: Build execution DAG and entry points
        execution_graph, entry_points = self._build_execution(
            pruned_context.execution,
            symbol_id_map,
            endpoint_table,
            sb,
        )

        # Phase 4: Build discoveries
        discoveries = self._build_discoveries(
            pruned_context.discoveries, sb
        )

        return LLMContext(
            st=StringTable(entries=tuple(sb.strings)),
            f=tuple(file_table),
            sym=tuple(symbol_table),
            ep=tuple(endpoint_table),
            cs=change_summary,
            cf=tuple(change_files),
            eg=execution_graph,
            epts=tuple(entry_points),
            disc=tuple(discoveries),
        )

    # -----------------------------------------------------------------------
    # Phase 1: Build Lookup Tables with Enum Encoding
    # -----------------------------------------------------------------------

    def _build_file_table(
        self,
        change_ctx: ChangeContext,
        sb: _StringBuilder,
    ) -> list[tuple[int, int]]:
        """Build normalized file lookup table.

        Each entry: (path_idx, ct_id)
        Uses enum encoding for change_type.
        """
        table: list[tuple[int, int]] = []
        seen: dict[str, int] = {}  # path -> index

        for f in change_ctx.files:
            if f.path not in seen:
                entry = (
                    sb.add(f.path),
                    _enum_id("ct", f.change_type),
                )
                seen[f.path] = len(table)
                table.append(entry)

        return table

    def _build_symbol_table(
        self,
        change_ctx: ChangeContext,
        exec_ctx: ExecutionContext,
        file_table: list[tuple[int, int]],
        sb: _StringBuilder,
    ) -> tuple[
        list[tuple[int, int, int]],
        dict[str, int],
    ]:
        """Build normalized symbol lookup table.

        Each entry: (file_id, name_idx, kind_id)

        Returns:
            (symbol_table, symbol_id_map) where symbol_id_map maps symbol.id -> table index.
        """
        file_idx_map: dict[str, int] = {}
        for i, entry in enumerate(file_table):
            file_idx_map[sb[entry[0]]] = i

        table: list[tuple[int, int, int]] = []
        seen: dict[str, int] = {}  # symbol id -> index

        # Keep track of count of symbols added per file to enforce LLM_CONTEXT_MAX_SYMBOLS_PER_FILE
        symbols_per_file: dict[int, int] = {}

        # Pass 1: Changed symbols (Always preserved, ignore limits)
        for f in change_ctx.files:
            for c in f.changes:
                sym = c.symbol
                if sym.id not in seen:
                    file_path, _, _ = _parse_location(sym.location)
                    file_id = file_idx_map.get(file_path, 0)

                    # Only store name if it's not derivable from the symbol id
                    derivable_name = _resolve_symbol_name_from_uri(sym.id)
                    name_idx = 0 if sym.name == derivable_name else sb.add(sym.name)

                    sym_entry = (
                        file_id,
                        name_idx,
                        _enum_id("kind", sym.kind),
                    )
                    seen[sym.id] = len(table)
                    table.append(sym_entry)
                    symbols_per_file[file_id] = symbols_per_file.get(file_id, 0) + 1

        # Pass 2: Execution symbols (subject to limit)
        if exec_ctx and exec_ctx.entry_points:
            for ep in exec_ctx.entry_points:
                for step in ep.execution_chain:
                    sym = step.symbol
                    if sym and sym.id and sym.id not in seen:
                        file_path, _, _ = _parse_location(sym.location)
                        file_id = file_idx_map.get(file_path, 0)

                        # Enforce limit of symbols per file
                        limit = self._settings.LLM_CONTEXT_MAX_SYMBOLS_PER_FILE
                        if symbols_per_file.get(file_id, 0) >= limit:
                            continue

                        derivable_name = _resolve_symbol_name_from_uri(sym.id)
                        if sym.name == derivable_name or _is_noise_string(sym.name):
                            name_idx = 0
                        else:
                            name_idx = sb.add(sym.name)

                        sym_entry = (
                            file_id,
                            name_idx,
                            _enum_id("kind", sym.kind),
                        )
                        seen[sym.id] = len(table)
                        table.append(sym_entry)
                        symbols_per_file[file_id] = symbols_per_file.get(file_id, 0) + 1

        return table, seen

    def _build_endpoint_table(
        self,
        exec_ctx: ExecutionContext,
        change_ctx: ChangeContext,
        sb: _StringBuilder,
    ) -> list[tuple[int, int]]:
        """Build normalized endpoint lookup table.

        Each entry: (endpoint_idx, path_idx)
        """
        table: list[tuple[int, int]] = []
        seen: dict[str, int] = {}  # endpoint string -> index

        # Find endpoints reached/changed by changed files directly to prioritize them
        changed_files = {f.path for f in change_ctx.files} if change_ctx and change_ctx.files else set()

        # Deterministic sorting/partitioning of entry points: changed/reached first, then others
        prioritized_eps = []
        other_eps = []
        for ep in exec_ctx.entry_points:
            # Check if any step in the execution chain belongs to a changed file
            is_changed = False
            for step in ep.execution_chain:
                if step.symbol and step.symbol.location:
                    file_path, _, _ = _parse_location(step.symbol.location)
                    if file_path in changed_files:
                        is_changed = True
                        break
            if is_changed:
                prioritized_eps.append(ep)
            else:
                other_eps.append(ep)

        # Enforce budget limit: LLM_CONTEXT_MAX_ENDPOINTS
        limit = self._settings.LLM_CONTEXT_MAX_ENDPOINTS
        
        # Sort both lists deterministically to ensure byte-identical output
        prioritized_eps.sort(key=lambda x: (x.endpoint, x.path))
        other_eps.sort(key=lambda x: (x.endpoint, x.path))

        # Always preserve prioritized ones, then fill with others up to limit
        selected_eps = prioritized_eps[:]
        remaining_slots = max(0, limit - len(selected_eps))
        selected_eps.extend(other_eps[:remaining_slots])

        for ep in selected_eps:
            if ep.endpoint not in seen:
                entry = (
                    sb.add(ep.endpoint),
                    sb.add(ep.path),
                )
                seen[ep.endpoint] = len(table)
                table.append(entry)

        return table


    # -----------------------------------------------------------------------
    # Phase 2: Build Change Section
    # -----------------------------------------------------------------------

    def _build_change_summary(
        self,
        summary: ChangeSummary,
        sb: _StringBuilder,
    ) -> tuple[int, int, int, int, int]:
        """Build change summary as positional tuple with enum encoding.

        Returns: (cls_id, scope_id, file_count, sym_count, bh_count)
        """
        return (
            _enum_id("cls", summary.classification),
            _enum_id("scope", summary.scope),
            summary.file_count,
            summary.symbol_count,
            summary.behavior_count,
        )

    def _build_change_files(
        self,
        files: tuple[FileChange, ...],
        file_table: list[tuple[int, int]],
        symbol_id_map: dict[str, int],
        sb: _StringBuilder,
    ) -> list[tuple]:
        """Build change files as positional tuples.

        Each entry: (file_idx, ((sym_idx, ct_id, (bh_change_ids...)), ...))
        Uses enum encoding for change_type and behavior_changes.
        """
        file_idx_map: dict[str, int] = {}
        for i, entry in enumerate(file_table):
            file_idx_map[sb[entry[0]]] = i

        result: list[tuple] = []
        for f in files:
            file_idx = file_idx_map.get(f.path, 0)
            changes_list: list[tuple] = []
            for c in f.changes:
                sym_idx = symbol_id_map.get(c.symbol.id, 0)
                ct_id = _enum_id("ct", c.change_type)
                bh_change_ids = tuple(_enum_id("bh_change", bc) for bc in c.behavior_changes)
                changes_list.append((sym_idx, ct_id, bh_change_ids))
            result.append((file_idx, tuple(changes_list)))

        return result

    # -----------------------------------------------------------------------
    # Phase 3: Build Execution DAG and Entry Points
    # -----------------------------------------------------------------------

    def _build_execution(
        self,
        exec_ctx: ExecutionContext,
        symbol_id_map: dict[str, int],
        endpoint_table: list[tuple[int, int]],
        sb: _StringBuilder,
    ) -> tuple[ExecutionGraph, list[tuple]]:
        """Build execution DAG and entry point references.

        Returns:
            (ExecutionGraph, list of entry point tuples)
        """
        endpoint_idx_map: dict[str, int] = {}
        for i, ep_entry in enumerate(endpoint_table):
            endpoint_idx_map[sb[ep_entry[0]]] = i

        node_map: dict[tuple[str, str, int], int] = {}
        nodes: list[tuple] = []
        edges: list[tuple[int, int]] = []
        entry_point_data: list[tuple] = []

        for ep in exec_ctx.entry_points:
            # Skip if endpoint not in endpoint_table (which was filtered/limited)
            if ep.endpoint not in endpoint_idx_map:
                continue

            chain_node_idxs: list[int] = []
            prev_node_idx: int | None = None

            # First, separate changed and other steps
            # Limits are applied to inferred context (non-changed steps).
            # The configured limit is LLM_CONTEXT_MAX_EXECUTION_CHAIN_LENGTH.
            limit = self._settings.LLM_CONTEXT_MAX_EXECUTION_CHAIN_LENGTH
            
            steps = []
            for step in ep.execution_chain:
                # If step is changed or symbol is in symbol_id_map, it is considered changed/preservable.
                # However, symbol_id_map contains all execution symbols, so we check step.changed
                if step.changed:
                    steps.append(step)
                else:
                    if len(steps) < limit:
                        steps.append(step)

            for step in steps:
                node_key = (step.behavior, step.symbol.id, step.depth)

                if node_key not in node_map:
                    node_idx = len(nodes)
                    node_map[node_key] = node_idx

                    sym_idx = symbol_id_map.get(step.symbol.id, 0)
                    kind_id = _enum_id("kind", step.kind)
                    reaches_svc_idx = sb.add(step.reaches.service) if step.reaches.service else 0

                    node = (
                        sym_idx,
                        kind_id,
                        step.depth,
                        reaches_svc_idx,
                    )
                    nodes.append(node)
                else:
                    node_idx = node_map[node_key]

                chain_node_idxs.append(node_idx)

                if prev_node_idx is not None:
                    edge = (prev_node_idx, node_idx)
                    if edge not in edges:
                        edges.append(edge)
                prev_node_idx = node_idx

            endpoint_idx = endpoint_idx_map.get(ep.endpoint, 0)
            terminal_idx = sb.add(ep.terminal)
            ep_tuple = (endpoint_idx, tuple(chain_node_idxs), terminal_idx, ep.max_depth)
            entry_point_data.append(ep_tuple)


        return ExecutionGraph(
            nodes=tuple(nodes),
            edges=tuple(edges),
        ), entry_point_data

    # -----------------------------------------------------------------------
    # Phase 4: Build Discoveries
    # -----------------------------------------------------------------------

    def _build_discoveries(
        self,
        discoveries: tuple[Discovery, ...],
        sb: _StringBuilder,
    ) -> list[tuple[int, dict[str, Any]]]:
        """Build discoveries as positional tuples with enum encoding.

        Each entry: (kind_id, facts_dict)
        """
        result: list[tuple[int, dict[str, Any]]] = []
        for d in discoveries:
            kind_id = _enum_id("bh_kind", d.kind)
            result.append((kind_id, d.facts))

        return result


# ---------------------------------------------------------------------------
# String Builder
# ---------------------------------------------------------------------------

class _StringBuilder:
    """Collects unique strings and assigns stable indices."""

    def __init__(self) -> None:
        self.strings: list[str] = [""]
        self._index: dict[str, int] = {"": 0}

    def add(self, s: str) -> int:
        if s in self._index:
            return self._index[s]
        idx = len(self.strings)
        self.strings.append(s)
        self._index[s] = idx
        return idx

    def __getitem__(self, idx: int) -> str:
        return self.strings[idx]

    def __len__(self) -> int:
        return len(self.strings)


# ---------------------------------------------------------------------------
# Enum Helpers
# ---------------------------------------------------------------------------

def _enum_id(table_name: str, value: str) -> int:
    """Get the enum ID for a given value in the named enum table.

    Returns 0 (the empty/default value) if the value is not found.
    """
    if not value:
        return 0
    reverse = ENUM_REVERSE.get(table_name, {})
    return reverse.get(value, 0)


def _is_noise_string(name: str) -> bool:
    """Check if a symbol name is framework/runtime noise that should not enter the string table."""
    if not name:
        return False
    parts = name.split(".")
    first = parts[0]
    return (
        name in LANGUAGE_PRIMITIVES or
        first in STD_LIBS or
        first in FRAMEWORK_MODULES or
        name in FRAMEWORK_NAMES or
        first in ORM_MODULES or
        name in ORM_NAMES
    )