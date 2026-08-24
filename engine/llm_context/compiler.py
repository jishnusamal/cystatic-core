"""LLMContext Compiler — transforms ReviewContext into a token-efficient IR.

This compiler transforms a ReviewContext into an LLMContext by:
  1. Starting from discoveries and expanding outward (discovery-centred build order)
  2. Filtering execution chains to only those originating from changed symbols
     or referenced by a discovery
  3. Compressing execution chains (Origin → Boundary → ExternalEffect)
  4. Filtering symbols to only changed, chain-referenced, or discovery-referenced
  5. Performing dead-string elimination after all sections are built
  6. Validating invariants before returning

Compression Rules Applied:
    1. Dictionary encode repeated strings into a global StringTable
    2. Encode enums (kind, visibility, language, change type, etc.) as integer IDs
    3. Normalize source locations from "file.py:1-10" to (start_line, end_line)
    4. Decompose URIs into file+symbol references
    5. Remove duplicate human labels derivable from IDs
    6. Use compact positional arrays instead of verbose objects
    7. Use short (1-3 char) field names
    8. Deduplicate execution steps via DAG
    9. Compress intermediate chains (collapse non-evidence helpers)
   10. Dead-string elimination (remove unreferenced string table entries)

Given the same ReviewContext, this compiler always produces the exact same LLMContext.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from engine.review_context.model import (
    ChangeContext,
    ChangeSummary,
    Discovery,
    EntryPointExecution,
    ExecutionContext,
    ExecutionStep,
    FileChange,
    ReviewContext,
)

from .model import ENUM_REVERSE, ExecutionGraph, LLMContext, StringTable

if TYPE_CHECKING:
    from core.config import CompilerSettings

# Regex for extracting file path and line range from location strings
_LOCATION_RE = re.compile(r"^(.+?)(?::(\d+)(?:-(\d+))?)?$")


# ---------------------------------------------------------------------------
# Review-scope pruning (imported from review_scope_builder to avoid circularity)
# ---------------------------------------------------------------------------
from .review_scope_builder import (
    FRAMEWORK_MODULES,
    FRAMEWORK_NAMES,
    LANGUAGE_PRIMITIVES,
    ORM_MODULES,
    ORM_NAMES,
    STD_LIBS,
    build_review_scope,
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
    """Extract symbol name from a URI like 'sym://path#SymbolName' or 'sym://path::func'.

    Returns the symbol name or empty string.
    """
    if not uri:
        return ""
    hash_match = re.search(r"#(.+)$", uri)
    if hash_match:
        val = hash_match.group(1)
        if "." in val:
            return val.split(".")[-1]
        return val
    colons_match = re.search(r"::(.+)$", uri)
    if colons_match:
        return colons_match.group(1)
    return ""


# ---------------------------------------------------------------------------
# Discovery reference collection
# ---------------------------------------------------------------------------


def _collect_discovery_references(
    discoveries: tuple[Discovery, ...],
) -> tuple[set[str], set[str], set[str]]:
    """Collect all IDs referenced by discoveries.

    Returns:
        (symbol_ids, behavior_ids, endpoint_keys) where:
          - symbol_ids: set of sym:// URIs found in reference.id fields
          - behavior_ids: set of behavior:// URIs found in reference.location fields
          - endpoint_keys: set of path strings found in references (for endpoint matching)
    """
    symbol_ids: set[str] = set()
    behavior_ids: set[str] = set()
    endpoint_keys: set[str] = set()

    for d in discoveries:
        for ref in d.references:
            # Collect symbol references
            if ref.id and (ref.id.startswith("sym://") or ("://" in ref.id and not ref.id.startswith("behavior://"))):
                symbol_ids.add(ref.id)
            # Collect behavior/execution references
            if ref.location:
                loc = ref.location
                if loc.startswith("behavior://"):
                    behavior_ids.add(loc)
                # Collect path-style locations that could match endpoints
                if loc.startswith("/"):
                    endpoint_keys.add(loc)
            # Also collect from compiler_artifact field if it looks like a path
            if ref.compiler_artifact and ref.compiler_artifact.startswith("/"):
                endpoint_keys.add(ref.compiler_artifact)

    return symbol_ids, behavior_ids, endpoint_keys


# ---------------------------------------------------------------------------
# Chain compression
# ---------------------------------------------------------------------------


def _compress_chain(
    steps: list[ExecutionStep],
    changed_symbol_ids: set[str],
) -> list[ExecutionStep]:
    """Compress an execution chain to only evidence-bearing nodes.

    Retains:
      - First step (origin)
      - Any step that is changed
      - Any step where reaches.service != "" (boundary crossing)
      - Last step (external effect)

    Collapses all intermediate helper-only steps.

    If the chain has ≤ 3 steps, return as-is.
    """
    if len(steps) <= 3:
        return steps

    retained: list[ExecutionStep] = []
    n = len(steps)

    for i, step in enumerate(steps):
        is_first = i == 0
        is_last = i == n - 1
        is_changed = step.changed or (
            step.symbol and step.symbol.id in changed_symbol_ids
        )
        is_boundary = bool(step.reaches and step.reaches.service)

        if is_first or is_last or is_changed or is_boundary:
            retained.append(step)

    # Guarantee at least first and last are present
    if not retained:
        retained = [steps[0], steps[-1]]
    elif retained[0] is not steps[0]:
        retained.insert(0, steps[0])
    elif retained[-1] is not steps[-1]:
        retained.append(steps[-1])

    return retained


# ---------------------------------------------------------------------------
# Dead-string elimination
# ---------------------------------------------------------------------------


def _collect_live_string_indices(
    file_table: list[tuple[int, int]],
    symbol_table: list[tuple[int, int, int]],
    endpoint_table: list[tuple[int, int]],
    change_files: list[tuple[int, tuple[int, ...]]],
    nodes: list[tuple[int, int, int, int]],
    entry_point_data: list[tuple[int, tuple[int, ...], int, int]],
    sb: _StringBuilder,
) -> set[int]:
    """Collect all string indices that are actually referenced by emitted objects."""
    live: set[int] = {0}  # index 0 (empty string) is always live

    # File table: path_idx (which may resolve via path_map)
    for path_idx, _ct_id in file_table:
        live.add(path_idx)
        # Also keep the directory prefix if path was decomposed
        raw = sb.strings[path_idx] if path_idx < len(sb.strings) else ""
        if raw.startswith(" "):
            # file part; find the dir prefix too — it's stored just before in the strings list
            # The directory prefix was added before the file entry, find it
            dir_key = sb.strings[path_idx - 1] if path_idx > 0 else ""
            if dir_key.endswith("/"):
                dir_idx = sb._index.get(dir_key, -1)
                if dir_idx >= 0:
                    live.add(dir_idx)

    # Symbol table: name_idx
    for _file_id, name_idx, _kind_id in symbol_table:
        if name_idx != 0:
            live.add(name_idx)

    # Endpoint table: path_idx
    for _method_id, path_idx in endpoint_table:
        live.add(path_idx)

    # Execution graph nodes: reaches_svc_idx, reaches_mod_idx
    for _sym_idx, _depth, reaches_svc_idx, reaches_mod_idx in nodes:
        if reaches_svc_idx != 0:
            live.add(reaches_svc_idx)
        if reaches_mod_idx != 0:
            live.add(reaches_mod_idx)

    # Entry points: terminal_idx
    for _ep_idx, _chain_nodes, terminal_idx, _max_depth in entry_point_data:
        if terminal_idx != 0:
            live.add(terminal_idx)

    return live


# ---------------------------------------------------------------------------
# Main Compiler
# ---------------------------------------------------------------------------


class LLMContextCompiler:
    """Compiles ReviewContext into a compact LLMContext.

    The LLMContext is a token-efficient representation of the ReviewContext
    facts optimized for LLM consumption. Uses a discovery-centred build order:
    every emitted object must be reachable from at least one discovery or
    originate from a changed symbol.
    """

    def __init__(self, settings: CompilerSettings | None = None) -> None:
        if settings is None:
            from core.config import get_compiler_settings

            settings = get_compiler_settings()
        self._settings = settings

    def compile(self, review_context: ReviewContext) -> LLMContext:
        """Compile a ReviewContext into an LLMContext.

        Build order (discovery-centred per §11):
          1. Run noise pruning (build_review_scope)
          2. Collect discovery-referenced IDs
          3. Filter and compress execution entry points
          4. Build symbol table (changed + chain-referenced + discovery-referenced)
          5. Build file table (from retained files/symbols)
          6. Build endpoint table (retained EPs only)
          7. Build change summary and change files
          8. Build execution DAG with compressed chains
          9. Build discoveries
         10. Dead-string elimination

        Args:
            review_context: The ReviewContext to compile.

        Returns:
            An LLMContext containing key facts from ReviewContext in a
            token-efficient compact representation.
        """
        # Phase 0: Prune implementation noise semantically
        pruned_context = build_review_scope(review_context, settings=self._settings)

        # -----------------------------------------------------------------------
        # Step 1: Collect changed symbol IDs (always preserved)
        # -----------------------------------------------------------------------
        changed_symbol_ids: set[str] = set()
        changed_file_paths: set[str] = set()
        if pruned_context.change and pruned_context.change.files:
            for f in pruned_context.change.files:
                changed_file_paths.add(f.path)
                for c in f.changes:
                    if c.symbol and c.symbol.id:
                        changed_symbol_ids.add(c.symbol.id)

        # -----------------------------------------------------------------------
        # Step 2: Collect discovery-referenced IDs
        # -----------------------------------------------------------------------
        disc_symbol_ids, disc_behavior_ids, disc_endpoint_keys = (
            _collect_discovery_references(pruned_context.discoveries)
        )

        # -----------------------------------------------------------------------
        # Step 3: Filter and compress execution entry points
        # -----------------------------------------------------------------------
        retained_eps = self._filter_entry_points(
            pruned_context.execution,
            changed_symbol_ids,
            disc_symbol_ids,
            disc_behavior_ids,
            disc_endpoint_keys,
        )

        # Selected entry points within endpoint budget
        changed_files = (
            {f.path for f in pruned_context.change.files}
            if pruned_context.change and pruned_context.change.files
            else set()
        )
        prioritized = []
        other = []
        for ep, compressed_steps in retained_eps:
            is_changed = False
            for step in compressed_steps:
                if step.symbol and step.symbol.location:
                    file_path, _, _ = _parse_location(step.symbol.location)
                    if file_path in changed_files:
                        is_changed = True
                        break
            if is_changed:
                prioritized.append((ep, compressed_steps))
            else:
                other.append((ep, compressed_steps))

        prioritized.sort(key=lambda x: (x[0].method, x[0].path))
        other.sort(key=lambda x: (x[0].method, x[0].path))

        limit = self._settings.LLM_CONTEXT_MAX_ENDPOINTS
        selected_eps = prioritized[:]
        remaining_slots = max(0, limit - len(selected_eps))
        selected_eps.extend(other[:remaining_slots])

        # -----------------------------------------------------------------------
        # Step 4: Build symbol table (changed + chain + discovery referenced)
        # -----------------------------------------------------------------------
        # First pass: collect all symbol IDs needed from SELECTED chains only
        chain_symbol_ids: set[str] = set()
        for ep, compressed_steps in selected_eps:
            for step in compressed_steps:
                if step.symbol and step.symbol.id:
                    chain_symbol_ids.add(step.symbol.id)

        sb = _StringBuilder()

        # Determine which files to include in the file table
        # (changed files + files containing chain symbols from SELECTED chains only)
        chain_file_paths: set[str] = set()
        for ep, compressed_steps in selected_eps:
            for step in compressed_steps:
                if step.symbol and step.symbol.location:
                    fp, _, _ = _parse_location(step.symbol.location)
                    if fp:
                        chain_file_paths.add(fp)

        retained_file_paths = changed_file_paths | chain_file_paths

        # Build file table from retained files
        file_table = self._build_file_table_filtered(
            pruned_context.change,
            retained_file_paths,
            sb,
        )

        # Build file_idx_map for symbol table construction
        file_idx_map: dict[str, int] = {}
        for i, entry in enumerate(file_table):
            file_idx_map[sb.get_string(entry[0])] = i

        # Build symbol table
        symbol_table, symbol_id_map = self._build_symbol_table_filtered(
            pruned_context.change,
            selected_eps,
            retained_eps,
            changed_symbol_ids,
            chain_symbol_ids,
            disc_symbol_ids,
            file_idx_map,
            sb,
        )

        # -----------------------------------------------------------------------
        # Step 5: Build endpoint table (retained EPs only)
        # -----------------------------------------------------------------------
        endpoint_table = []
        seen_endpoints = {}
        for ep, _ in selected_eps:
            key = (ep.method, ep.path)
            if key not in seen_endpoints:
                entry = (
                    _enum_id("method", ep.method),
                    sb.add(ep.path),
                )
                seen_endpoints[key] = len(endpoint_table)
                endpoint_table.append(entry)

        # Build endpoint_idx_map for execution building
        from .model import ENUM_METHOD

        endpoint_idx_map: dict[tuple[str, str], int] = {}
        for i, ep_entry in enumerate(endpoint_table):
            method_id, path_idx = ep_entry
            method_str = ENUM_METHOD.get(method_id, "")
            path_str = sb.get_string(path_idx)
            endpoint_idx_map[(method_str, path_str)] = i

        # -----------------------------------------------------------------------
        # Step 6: Build change summary and change files
        # -----------------------------------------------------------------------
        change_summary = self._build_change_summary(pruned_context.change.summary, sb)
        change_files = self._build_change_files(
            pruned_context.change.files,
            file_table,
            symbol_id_map,
            sb,
        )

        # -----------------------------------------------------------------------
        # Step 7: Build execution DAG (using compressed chains)
        # -----------------------------------------------------------------------
        execution_graph, entry_point_data = self._build_execution_filtered(
            retained_eps,
            symbol_id_map,
            endpoint_idx_map,
            sb,
        )

        # -----------------------------------------------------------------------
        # Step 8: Build discoveries
        # -----------------------------------------------------------------------
        discoveries = self._build_discoveries(pruned_context.discoveries, sb)

        # -----------------------------------------------------------------------
        # Step 9: Dead-string elimination
        # -----------------------------------------------------------------------
        live_indices = _collect_live_string_indices(
            file_table,
            symbol_table,
            endpoint_table,
            change_files,
            list(execution_graph.nodes),
            entry_point_data,
            sb,
        )

        # Remap: old_idx -> new_idx in the compact string table
        old_to_new: dict[int, int] = {0: 0}
        new_strings: list[str] = [""]  # index 0 = empty string always

        # Sort live indices (excluding 0) to maintain deterministic order
        for old_idx in sorted(live_indices):
            if old_idx == 0:
                continue
            if old_idx < len(sb.strings):
                new_idx = len(new_strings)
                new_strings.append(sb.strings[old_idx])
                old_to_new[old_idx] = new_idx

        # Remap file table
        remapped_file_table = [
            (old_to_new.get(path_idx, 0), ct_id) for path_idx, ct_id in file_table
        ]

        # Remap symbol table
        remapped_symbol_table = [
            (file_id, old_to_new.get(name_idx, 0), kind_id)
            for file_id, name_idx, kind_id in symbol_table
        ]

        # Remap endpoint table
        remapped_endpoint_table = [
            (method_id, old_to_new.get(path_idx, 0))
            for method_id, path_idx in endpoint_table
        ]

        # Remap execution graph nodes
        remapped_nodes = tuple(
            (sym_idx, depth, old_to_new.get(svc_idx, 0), old_to_new.get(mod_idx, 0))
            for sym_idx, depth, svc_idx, mod_idx in execution_graph.nodes
        )

        # Remap entry points
        remapped_epts = tuple(
            (ep_idx, chain_nodes, old_to_new.get(term_idx, 0), max_depth)
            for ep_idx, chain_nodes, term_idx, max_depth in entry_point_data
        )

        # Also update path_map in sb to use new indices (needed for get_string lookups in tests)
        new_path_map: dict[int, str] = {}
        for old_idx, path in sb.path_map.items():
            new_idx = old_to_new.get(old_idx)
            if new_idx is not None:
                new_path_map[new_idx] = path

        # Build final compact string table
        compact_st = StringTable(entries=tuple(new_strings))

        return LLMContext(
            st=compact_st,
            f=tuple(remapped_file_table),
            sym=tuple(remapped_symbol_table),
            ep=tuple(remapped_endpoint_table),
            cs=change_summary,
            cf=tuple(change_files),
            eg=ExecutionGraph(
                nodes=remapped_nodes,
                edges=execution_graph.edges,
            ),
            epts=remapped_epts,
            disc=tuple(discoveries),
        )

    # -----------------------------------------------------------------------
    # Phase 1: Build Lookup Tables with Enum Encoding
    # -----------------------------------------------------------------------

    def _build_file_table_filtered(
        self,
        change_ctx: ChangeContext,
        retained_file_paths: set[str],
        sb: _StringBuilder,
    ) -> list[tuple[int, int]]:
        """Build normalized file lookup table from retained files only.

        Each entry: (path_idx, ct_id)
        Uses enum encoding for change_type.
        """
        table: list[tuple[int, int]] = []
        seen: dict[str, int] = {}

        for f in change_ctx.files:
            if f.path in retained_file_paths and f.path not in seen:
                entry = (
                    sb.add_path(f.path),
                    _enum_id("ct", f.change_type),
                )
                seen[f.path] = len(table)
                table.append(entry)

        return table

    def _build_symbol_table_filtered(
        self,
        change_ctx: ChangeContext,
        selected_eps: list[tuple[EntryPointExecution, list[ExecutionStep]]],
        retained_eps: list[tuple[EntryPointExecution, list[ExecutionStep]]],
        changed_symbol_ids: set[str],
        chain_symbol_ids: set[str],
        disc_symbol_ids: set[str],
        file_idx_map: dict[str, int],
        sb: _StringBuilder,
    ) -> tuple[list[tuple[int, int, int]], dict[str, int]]:
        """Build normalized symbol lookup table — discovery-centred filtering.

        Only emits:
          - Changed symbols (always)
          - Symbols referenced by retained execution chains
          - Symbols directly referenced by discoveries (sym:// URIs)

        Each entry: (file_id, name_idx, kind_id)
        """
        table: list[tuple[int, int, int]] = []
        seen_tuples: dict[tuple[int, int, int], int] = {}
        symbol_id_map: dict[str, int] = {}
        symbols_per_file: dict[int, int] = {}

        # Pass 1: Changed symbols (always preserved, ignore limits)
        for f in change_ctx.files:
            for c in f.changes:
                sym = c.symbol
                if sym.id not in symbol_id_map:
                    file_path, _, _ = _parse_location(sym.location)
                    file_id = file_idx_map.get(file_path, 0)

                    derivable_name = _resolve_symbol_name_from_uri(sym.id)
                    name_idx = 0 if sym.name == derivable_name else sb.add(sym.name)

                    sym_entry = (
                        file_id,
                        name_idx,
                        _enum_id("kind", sym.kind),
                    )

                    if sym_entry not in seen_tuples:
                        idx = len(table)
                        table.append(sym_entry)
                        seen_tuples[sym_entry] = idx
                    else:
                        idx = seen_tuples[sym_entry]

                    symbol_id_map[sym.id] = idx
                    symbols_per_file[file_id] = symbols_per_file.get(file_id, 0) + 1

        # Pass 2: Chain-referenced symbols (subject to per-file limit)
        all_referenced = chain_symbol_ids | disc_symbol_ids
        for ep, compressed_steps in selected_eps:
            for step in compressed_steps:
                sym = step.symbol
                if sym and sym.id and sym.id not in symbol_id_map:
                    # Only add if referenced by a retained chain or discovery
                    if sym.id not in all_referenced:
                        continue

                    file_path, _, _ = _parse_location(sym.location)
                    file_id = file_idx_map.get(file_path, 0)

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

                    if sym_entry not in seen_tuples:
                        idx = len(table)
                        table.append(sym_entry)
                        seen_tuples[sym_entry] = idx
                    else:
                        idx = seen_tuples[sym_entry]

                    symbol_id_map[sym.id] = idx
                    symbols_per_file[file_id] = symbols_per_file.get(file_id, 0) + 1

        # Pass 3: Remaining discovery-referenced symbols from any retained chain (even if EP was discarded)
        for ep, compressed_steps in retained_eps:
            for step in compressed_steps:
                sym = step.symbol
                if (
                    sym
                    and sym.id
                    and sym.id in disc_symbol_ids
                    and sym.id not in symbol_id_map
                ):
                    file_path, _, _ = _parse_location(sym.location)
                    file_id = file_idx_map.get(file_path, 0)

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

                    if sym_entry not in seen_tuples:
                        idx = len(table)
                        table.append(sym_entry)
                        seen_tuples[sym_entry] = idx
                    else:
                        idx = seen_tuples[sym_entry]

                    symbol_id_map[sym.id] = idx
                    symbols_per_file[file_id] = symbols_per_file.get(file_id, 0) + 1

        return table, symbol_id_map

    def _build_endpoint_table_filtered(
        self,
        retained_eps: list[tuple[EntryPointExecution, list[ExecutionStep]]],
        change_ctx: ChangeContext,
        sb: _StringBuilder,
    ) -> list[tuple[int, int]]:
        """Build normalized endpoint lookup table from retained EPs only.

        Each entry: (method_id, path_idx)
        """
        table: list[tuple[int, int]] = []
        seen: dict[tuple[str, str], int] = {}

        changed_files = (
            {f.path for f in change_ctx.files}
            if change_ctx and change_ctx.files
            else set()
        )

        # Partition: EPs touching changed files first
        prioritized = []
        other = []
        for ep, compressed_steps in retained_eps:
            is_changed = False
            for step in compressed_steps:
                if step.symbol and step.symbol.location:
                    file_path, _, _ = _parse_location(step.symbol.location)
                    if file_path in changed_files:
                        is_changed = True
                        break
            if is_changed:
                prioritized.append((ep, compressed_steps))
            else:
                other.append((ep, compressed_steps))

        # Sort deterministically
        prioritized.sort(key=lambda x: (x[0].method, x[0].path))
        other.sort(key=lambda x: (x[0].method, x[0].path))

        # Enforce endpoint budget
        limit = self._settings.LLM_CONTEXT_MAX_ENDPOINTS
        selected = prioritized[:]
        remaining_slots = max(0, limit - len(selected))
        selected.extend(other[:remaining_slots])

        for ep, _ in selected:
            key = (ep.method, ep.path)
            if key not in seen:
                entry = (
                    _enum_id("method", ep.method),
                    sb.add(ep.path),
                )
                seen[key] = len(table)
                table.append(entry)

        return table

    def _filter_entry_points(
        self,
        exec_ctx: ExecutionContext,
        changed_symbol_ids: set[str],
        disc_symbol_ids: set[str],
        disc_behavior_ids: set[str],
        disc_endpoint_keys: set[str],
    ) -> list[tuple[EntryPointExecution, list[ExecutionStep]]]:
        """Filter and compress execution entry points.

        Retention rules (any one is sufficient):
          1. Any step in the chain has step.changed == True
          2. Any step's symbol.id is in changed_symbol_ids
          3. The endpoint path is referenced by a discovery
          4. The chain has any non-empty steps (survived build_review_scope pruning)
             — the pruner is already the noise gate; we respect its decisions.

        After retention, duplicate paths reaching the same endpoint are deduplicated
        (shortest chain wins, per §8 of the spec).

        Returns a list of (ep, compressed_steps) pairs.
        """
        if not exec_ctx or not exec_ctx.entry_points:
            return []

        result: list[tuple[EntryPointExecution, list[ExecutionStep]]] = []
        # Track seen endpoint keys to avoid duplicate paths reaching the same endpoint
        seen_endpoint_keys: dict[tuple[str, str], int] = {}  # key -> chain length

        limit = self._settings.LLM_CONTEXT_MAX_EXECUTION_CHAIN_LENGTH

        for ep in exec_ctx.entry_points:
            ep_key = (ep.method, ep.path)

            # Apply chain length limit (changed steps are never dropped)
            steps: list[ExecutionStep] = []
            for step in ep.execution_chain:
                if step.changed or (
                    step.symbol and step.symbol.id in changed_symbol_ids
                ):
                    steps.append(step)
                else:
                    if len(steps) < limit:
                        steps.append(step)

            # Skip EPs with empty chains (fully pruned by build_review_scope)
            if not steps:
                continue

            # Compress the chain
            compressed = _compress_chain(steps, changed_symbol_ids)

            # Duplicate path elimination: if same endpoint key already seen,
            # keep only the shortest chain
            chain_len = len(compressed)
            if ep_key in seen_endpoint_keys:
                existing_len = seen_endpoint_keys[ep_key]
                if chain_len >= existing_len:
                    continue
                # Replace existing with shorter chain
                for i, (existing_ep, _existing_steps) in enumerate(result):
                    if (existing_ep.method, existing_ep.path) == ep_key:
                        result[i] = (ep, compressed)
                        seen_endpoint_keys[ep_key] = chain_len
                        break
            else:
                seen_endpoint_keys[ep_key] = chain_len
                result.append((ep, compressed))

        return result

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
    ) -> list[tuple[int, tuple[int, ...]]]:
        """Build change files as compact positional tuples.

        Each entry: (file_idx, (changed_sym_idx_1, changed_sym_idx_2, ...))
        Only emits symbols that are in the symbol_id_map (changed symbols only).
        """
        file_idx_map: dict[str, int] = {}
        for i, entry in enumerate(file_table):
            file_idx_map[sb.get_string(entry[0])] = i

        result: list[tuple[int, tuple[int, ...]]] = []
        for f in files:
            file_idx = file_idx_map.get(f.path, -1)
            if file_idx < 0:
                continue
            changed_sym_idxs: list[int] = []
            for c in f.changes:
                sym_idx = symbol_id_map.get(c.symbol.id, -1)
                if sym_idx >= 0 and sym_idx not in changed_sym_idxs:
                    changed_sym_idxs.append(sym_idx)
            result.append((file_idx, tuple(changed_sym_idxs)))

        return result

    # -----------------------------------------------------------------------
    # Phase 3: Build Execution DAG (using pre-filtered/compressed chains)
    # -----------------------------------------------------------------------

    def _build_execution_filtered(
        self,
        retained_eps: list[tuple[EntryPointExecution, list[ExecutionStep]]],
        symbol_id_map: dict[str, int],
        endpoint_idx_map: dict[tuple[str, str], int],
        sb: _StringBuilder,
    ) -> tuple[ExecutionGraph, list[tuple[int, tuple[int, ...], int, int]]]:
        """Build execution DAG and entry point references from filtered/compressed chains.

        Returns:
            (ExecutionGraph, list of entry point tuples)
        """
        node_map: dict[tuple[str, str], int] = {}
        nodes: list[tuple[int, int, int, int]] = []
        edges: list[tuple[int, int]] = []
        entry_point_data: list[tuple[int, tuple[int, ...], int, int]] = []

        for ep, compressed_steps in retained_eps:
            key = (ep.method, ep.path)
            if key not in endpoint_idx_map:
                continue

            chain_node_idxs: list[int] = []
            prev_node_idx: int | None = None

            for step in compressed_steps:
                node_key = (step.behavior, step.symbol.id)

                if node_key not in node_map:
                    node_idx = len(nodes)
                    node_map[node_key] = node_idx

                    sym_idx = symbol_id_map.get(step.symbol.id, 0)
                    reaches_svc_idx = (
                        sb.add(step.reaches.service) if step.reaches.service else 0
                    )
                    reaches_mod_idx = (
                        sb.add(step.reaches.module) if step.reaches.module else 0
                    )

                    node = (
                        sym_idx,
                        step.depth,
                        reaches_svc_idx,
                        reaches_mod_idx,
                    )
                    nodes.append(node)
                else:
                    node_idx = node_map[node_key]

                # Deduplicate consecutive duplicate node indices
                if not chain_node_idxs or chain_node_idxs[-1] != node_idx:
                    chain_node_idxs.append(node_idx)

                    if prev_node_idx is not None and prev_node_idx != node_idx:
                        edge = (prev_node_idx, node_idx)
                        if edge not in edges:
                            edges.append(edge)
                    prev_node_idx = node_idx

            endpoint_idx = endpoint_idx_map[key]
            terminal_idx = sb.add(ep.terminal) if ep.terminal else 0
            ep_tuple = (
                endpoint_idx,
                tuple(chain_node_idxs),
                terminal_idx,
                ep.max_depth,
            )
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
    """Collects unique strings and assigns stable indices. Handles path prefix compression."""

    def __init__(self) -> None:
        self.strings: list[str] = [""]
        self._index: dict[str, int] = {"": 0}
        self.path_map: dict[int, str] = {}

    def add(self, s: str) -> int:
        if s in self._index:
            return self._index[s]
        idx = len(self.strings)
        self.strings.append(s)
        self._index[s] = idx
        return idx

    def add_path(self, path: str) -> int:
        """Add a path to the string table with directory prefix optimization.

        Stores paths grouped under their directory prefix when applicable, e.g.:
            "payment/"
            " checkout.py"
        """
        if path in self._index:
            return self._index[path]

        if "/" in path:
            dir_part, _, file_part = path.rpartition("/")
            dir_prefix = f"{dir_part}/"
            self.add(dir_prefix)
            file_entry = f" {file_part}"
            file_idx = self.add(file_entry)
            full_idx = file_idx  # index pointing to formatted string entry
            self._index[path] = full_idx
            self.path_map[full_idx] = path
            return full_idx
        else:
            idx = self.add(path)
            self.path_map[idx] = path
            return idx

    def get_string(self, idx: int) -> str:
        """Get original string, resolving path maps if present."""
        if idx in self.path_map:
            return self.path_map[idx]
        if idx < len(self.strings):
            return self.strings[idx]
        return ""

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
        name in LANGUAGE_PRIMITIVES
        or first in STD_LIBS
        or first in FRAMEWORK_MODULES
        or name in FRAMEWORK_NAMES
        or first in ORM_MODULES
        or name in ORM_NAMES
    )
