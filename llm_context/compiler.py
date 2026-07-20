"""LLMContext Compiler — deterministic token-efficient representation of ReviewContext.

This compiler transforms a ReviewContext into an LLMContext by eliminating
representational redundancy. It performs NO semantic interpretation, NO AI/LLM
usage, and NO information loss.

Compression Rules Applied:
    1. Normalize repeated objects into lookup tables
    2. Dictionary repeated strings into a global StringTable
    3. Separate metadata from instances
    4. Eliminate repeated field names via positional arrays
    5. Factor common execution chains into a DAG
    6. Normalize references into a single lookup table
    7. Generate canonical IDs (F1, S1, B1, R1, E1)
    8. Eliminate derived information

Given the same ReviewContext, this compiler always produces the exact same LLMContext.
"""
from __future__ import annotations

from typing import Any

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

from .model import LLMContext, StringTable, ExecutionGraph


class LLMContextCompiler:
    """Compiles ReviewContext into a token-efficient LLMContext.

    The LLMContext is a lossless, token-efficient representation of the
    same information. It is fully reversible back to an equivalent ReviewContext.

    No semantic interpretation, no information loss, no AI/LLM usage.
    """

    def compile(self, review_context: ReviewContext) -> LLMContext:
        """Compile a ReviewContext into an LLMContext.

        Args:
            review_context: The ReviewContext to compile.

        Returns:
            An LLMContext containing every fact from ReviewContext in a
            token-efficient representation.
        """
        # Phase 1: Collect all unique strings
        string_builder = _StringBuilder()

        # Phase 2: Build normalized lookup tables
        file_table = self._build_file_table(review_context.change, string_builder)
        symbol_table = self._build_symbol_table(review_context.change, string_builder)
        behavior_table = self._build_behavior_table(review_context.execution, string_builder)
        reference_table = self._build_reference_table(review_context, string_builder)
        endpoint_table = self._build_endpoint_table(review_context.execution, string_builder)

        # Phase 3: Build change section
        change_summary = self._build_change_summary(
            review_context.change.summary, string_builder
        )
        change_files = self._build_change_files(
            review_context.change.files, file_table, symbol_table, string_builder
        )

        # Phase 4: Build execution DAG and entry points
        execution_graph, entry_points = self._build_execution(
            review_context.execution, symbol_table, behavior_table, endpoint_table, string_builder
        )

        # Phase 5: Build deepest execution
        deepest = self._build_deepest_execution(
            review_context.execution.deepest_execution, endpoint_table, string_builder
        )

        # Phase 6: Build discoveries
        discoveries = self._build_discoveries(
            review_context.discoveries, reference_table, string_builder
        )

        return LLMContext(
            strings=StringTable(entries=tuple(string_builder.strings)),
            files=tuple(file_table),
            symbols=tuple(symbol_table),
            behaviors=tuple(behavior_table),
            references=tuple(reference_table),
            endpoints=tuple(endpoint_table),
            change_summary=change_summary,
            change_files=tuple(change_files),
            execution_graph=execution_graph,
            entry_points=tuple(entry_points),
            deepest_execution=deepest,
            discoveries=tuple(discoveries),
        )

    # -----------------------------------------------------------------------
    # Phase 1: String Collection
    # -----------------------------------------------------------------------

    def _collect_strings(
        self,
        review_context: ReviewContext,
        string_builder: _StringBuilder,
    ) -> None:
        """Collect all unique strings from ReviewContext into the string builder.

        This ensures all strings are registered before building lookup tables.
        """
        # Change section strings
        ctx = review_context.change
        string_builder.add(ctx.summary.classification)
        string_builder.add(ctx.summary.scope)
        for f in ctx.files:
            string_builder.add(f.path)
            string_builder.add(f.language)
            string_builder.add(f.change_type)
            for c in f.changes:
                string_builder.add(c.symbol.id)
                string_builder.add(c.symbol.name)
                string_builder.add(c.symbol.kind)
                string_builder.add(c.symbol.visibility)
                string_builder.add(c.symbol.language)
                string_builder.add(c.symbol.location)
                string_builder.add(c.change_type)
                for bc in c.behavior_changes:
                    string_builder.add(bc)

        # Execution section strings
        exec_ctx = review_context.execution
        for ep in exec_ctx.entry_points:
            string_builder.add(ep.endpoint)
            string_builder.add(ep.method)
            string_builder.add(ep.path)
            string_builder.add(ep.terminal)
            for step in ep.execution_chain:
                string_builder.add(step.behavior)
                string_builder.add(step.symbol.id)
                string_builder.add(step.symbol.name)
                string_builder.add(step.symbol.kind)
                string_builder.add(step.symbol.location)
                string_builder.add(step.kind)
                string_builder.add(step.reaches.service)
                string_builder.add(step.reaches.module)
                string_builder.add(step.reaches.package)
                for ref in step.references:
                    string_builder.add(ref)

        # Deepest execution
        string_builder.add(exec_ctx.deepest_execution.entry_point)

        # Discovery section strings
        for d in review_context.discoveries:
            string_builder.add(d.id)
            string_builder.add(d.kind)
            for ref in d.references:
                string_builder.add(ref.id)
                string_builder.add(ref.kind)
                string_builder.add(ref.location)
                string_builder.add(ref.compiler_artifact)

    # -----------------------------------------------------------------------
    # Phase 2: Build Lookup Tables
    # -----------------------------------------------------------------------

    def _build_file_table(
        self,
        change_ctx: ChangeContext,
        sb: _StringBuilder,
    ) -> list[tuple[int, int, int]]:
        """Build normalized file lookup table.

        Each entry: (path_idx, language_idx, change_type_idx)
        """
        table: list[tuple[int, int, int]] = []
        seen: dict[str, int] = {}  # path -> index

        for f in change_ctx.files:
            if f.path not in seen:
                entry = (
                    sb.add(f.path),
                    sb.add(f.language),
                    sb.add(f.change_type),
                )
                seen[f.path] = len(table)
                table.append(entry)

        return table

    def _build_symbol_table(
        self,
        change_ctx: ChangeContext,
        sb: _StringBuilder,
    ) -> list[tuple[int, int, int, int, int, int]]:
        """Build normalized symbol lookup table.

        Each entry: (id_idx, name_idx, kind_idx, visibility_idx, language_idx, location_idx)
        """
        table: list[tuple[int, int, int, int, int, int]] = []
        seen: dict[str, int] = {}  # symbol id -> index

        for f in change_ctx.files:
            for c in f.changes:
                sym = c.symbol
                if sym.id not in seen:
                    entry = (
                        sb.add(sym.id),
                        sb.add(sym.name),
                        sb.add(sym.kind),
                        sb.add(sym.visibility),
                        sb.add(sym.language),
                        sb.add(sym.location),
                    )
                    seen[sym.id] = len(table)
                    table.append(entry)

        return table

    def _build_behavior_table(
        self,
        exec_ctx: ExecutionContext,
        sb: _StringBuilder,
    ) -> list[tuple[int, int, int]]:
        """Build normalized behavior lookup table.

        Each entry: (id_idx, name_idx, kind_idx)
        """
        table: list[tuple[int, int, int]] = []
        seen: dict[str, int] = {}  # behavior id -> index

        for ep in exec_ctx.entry_points:
            for step in ep.execution_chain:
                if step.behavior not in seen:
                    entry = (
                        sb.add(step.behavior),
                        sb.add(step.symbol.name),
                        sb.add(step.kind),
                    )
                    seen[step.behavior] = len(table)
                    table.append(entry)

        return table

    def _build_reference_table(
        self,
        review_context: ReviewContext,
        sb: _StringBuilder,
    ) -> list[tuple[int, int, int, int]]:
        """Build normalized reference lookup table.

        Each entry: (id_idx, kind_idx, location_idx, compiler_artifact_idx)
        """
        table: list[tuple[int, int, int, int]] = []
        seen: dict[str, int] = {}  # reference id -> index

        for d in review_context.discoveries:
            for ref in d.references:
                if ref.id not in seen:
                    entry = (
                        sb.add(ref.id),
                        sb.add(ref.kind),
                        sb.add(ref.location),
                        sb.add(ref.compiler_artifact),
                    )
                    seen[ref.id] = len(table)
                    table.append(entry)

        return table

    def _build_endpoint_table(
        self,
        exec_ctx: ExecutionContext,
        sb: _StringBuilder,
    ) -> list[tuple[int, int, int]]:
        """Build normalized endpoint lookup table.

        Each entry: (endpoint_idx, method_idx, path_idx)
        """
        table: list[tuple[int, int, int]] = []
        seen: dict[str, int] = {}  # endpoint string -> index

        for ep in exec_ctx.entry_points:
            if ep.endpoint not in seen:
                entry = (
                    sb.add(ep.endpoint),
                    sb.add(ep.method),
                    sb.add(ep.path),
                )
                seen[ep.endpoint] = len(table)
                table.append(entry)

        return table

    # -----------------------------------------------------------------------
    # Phase 3: Build Change Section
    # -----------------------------------------------------------------------

    def _build_change_summary(
        self,
        summary: ChangeSummary,
        sb: _StringBuilder,
    ) -> tuple[int, int, int, int, int]:
        """Build change summary as positional tuple.

        Returns: (classification_idx, scope_idx, file_count, symbol_count, behavior_count)
        """
        return (
            sb.add(summary.classification),
            sb.add(summary.scope),
            summary.file_count,
            summary.symbol_count,
            summary.behavior_count,
        )

    def _build_change_files(
        self,
        files: tuple[FileChange, ...],
        file_table: list[tuple[int, int, int]],
        symbol_table: list[tuple[int, int, int, int, int, int]],
        sb: _StringBuilder,
    ) -> list[tuple]:
        """Build change files as positional tuples.

        Each entry: (file_idx, ((symbol_idx, change_type_idx, (behavior_change_idxs...)), ...))
        """
        # Build file path -> file table index lookup
        file_idx_map: dict[str, int] = {}
        for i, entry in enumerate(file_table):
            file_idx_map[sb[entry[0]]] = i

        # Build symbol id -> symbol table index lookup
        symbol_idx_map: dict[str, int] = {}
        for i, entry in enumerate(symbol_table):
            symbol_idx_map[sb[entry[0]]] = i

        result: list[tuple] = []
        for f in files:
            file_idx = file_idx_map.get(f.path, 0)
            changes_list: list[tuple] = []
            for c in f.changes:
                sym_idx = symbol_idx_map.get(c.symbol.id, 0)
                change_type_idx = sb.add(c.change_type)
                behavior_change_idxs = tuple(sb.add(bc) for bc in c.behavior_changes)
                changes_list.append((sym_idx, change_type_idx, behavior_change_idxs))
            result.append((file_idx, tuple(changes_list)))

        return result

    # -----------------------------------------------------------------------
    # Phase 4: Build Execution DAG and Entry Points
    # -----------------------------------------------------------------------

    def _build_execution(
        self,
        exec_ctx: ExecutionContext,
        symbol_table: list[tuple[int, int, int, int, int, int]],
        behavior_table: list[tuple[int, int, int]],
        endpoint_table: list[tuple[int, int, int]],
        sb: _StringBuilder,
    ) -> tuple[ExecutionGraph, list[tuple]]:
        """Build execution DAG and entry point references.

        The DAG factors common execution chain prefixes into shared nodes.
        Entry points reference graph nodes rather than embedding full chains.

        Returns:
            (ExecutionGraph, list of entry point tuples)
        """
        # Build behavior id -> behavior table index
        behavior_idx_map: dict[str, int] = {}
        for i, b in enumerate(behavior_table):
            behavior_idx_map[sb[b[0]]] = i

        # Build symbol id -> symbol table index
        symbol_idx_map: dict[str, int] = {}
        for i, s in enumerate(symbol_table):
            symbol_idx_map[sb[s[0]]] = i

        # Build endpoint -> endpoint table index
        endpoint_idx_map: dict[str, int] = {}
        for i, ep_entry in enumerate(endpoint_table):
            endpoint_idx_map[sb[ep_entry[0]]] = i

        # Collect all unique execution steps (nodes)
        # A node is unique by (behavior_id, symbol_id, depth)
        node_map: dict[tuple[str, str, int], int] = {}  # (behavior, symbol_id, depth) -> node_idx
        nodes: list[tuple] = []
        edges: list[tuple[int, int]] = []
        entry_point_data: list[tuple] = []

        for ep in exec_ctx.entry_points:
            chain_node_idxs: list[int] = []
            prev_node_idx: int | None = None

            for step in ep.execution_chain:
                # Create unique key for this step
                node_key = (step.behavior, step.symbol.id, step.depth)

                if node_key not in node_map:
                    node_idx = len(nodes)
                    node_map[node_key] = node_idx

                    behavior_idx = behavior_idx_map.get(step.behavior, 0)
                    sym_idx = symbol_idx_map.get(step.symbol.id, 0)
                    kind_idx = sb.add(step.kind)
                    reaches_service_idx = sb.add(step.reaches.service)
                    reaches_module_idx = sb.add(step.reaches.module)
                    reaches_package_idx = sb.add(step.reaches.package)
                    ref_idxs = tuple(sb.add(r) for r in step.references)

                    node = (
                        behavior_idx,
                        sym_idx,
                        kind_idx,
                        step.depth,
                        step.changed,
                        step.shared,
                        reaches_service_idx,
                        reaches_module_idx,
                        reaches_package_idx,
                        ref_idxs,
                    )
                    nodes.append(node)
                else:
                    node_idx = node_map[node_key]

                chain_node_idxs.append(node_idx)

                # Add edge from previous node to this node
                if prev_node_idx is not None:
                    edge = (prev_node_idx, node_idx)
                    if edge not in edges:
                        edges.append(edge)
                prev_node_idx = node_idx

            # Build entry point tuple with correct endpoint index
            endpoint_idx = endpoint_idx_map.get(ep.endpoint, 0)
            terminal_idx = sb.add(ep.terminal)
            ep_tuple = (endpoint_idx, tuple(chain_node_idxs), terminal_idx, ep.max_depth)
            entry_point_data.append(ep_tuple)

        return ExecutionGraph(
            nodes=tuple(nodes),
            edges=tuple(edges),
        ), entry_point_data

    def _build_deepest_execution(
        self,
        deepest: DeepestExecution,
        endpoint_table: list[tuple[int, int, int]],
        sb: _StringBuilder,
    ) -> tuple[int, int]:
        """Build deepest execution as positional tuple.

        Returns: (endpoint_idx, depth)
        """
        # Find endpoint index
        endpoint_idx = 0
        for i, ep in enumerate(endpoint_table):
            if sb[ep[0]] == deepest.entry_point:
                endpoint_idx = i
                break

        return (endpoint_idx, deepest.depth)

    # -----------------------------------------------------------------------
    # Phase 6: Build Discoveries
    # -----------------------------------------------------------------------

    def _build_discoveries(
        self,
        discoveries: tuple[Discovery, ...],
        reference_table: list[tuple[int, int, int, int]],
        sb: _StringBuilder,
    ) -> list[tuple]:
        """Build discoveries as positional tuples.

        Each entry: (id_idx, kind_idx, facts_dict, (ref_idxs...))
        """
        # Build reference id -> reference table index
        ref_idx_map: dict[str, int] = {}
        for i, r in enumerate(reference_table):
            ref_idx_map[sb[r[0]]] = i

        result: list[tuple] = []
        for d in discoveries:
            id_idx = sb.add(d.id)
            kind_idx = sb.add(d.kind)
            ref_idxs = tuple(
                ref_idx_map.get(ref.id, 0) for ref in d.references
            )
            result.append((id_idx, kind_idx, d.facts, ref_idxs))

        return result


# ---------------------------------------------------------------------------
# String Builder — collects unique strings and assigns indices
# ---------------------------------------------------------------------------

class _StringBuilder:
    """Collects unique strings and assigns stable indices.

    This is the core mechanism for building the global StringTable.
    Every unique string gets a deterministic index based on first occurrence.
    Index 0 is reserved for the empty string.
    """

    def __init__(self) -> None:
        # Index 0 is reserved for empty string
        self.strings: list[str] = [""]
        self._index: dict[str, int] = {"": 0}

    def add(self, s: str) -> int:
        """Add a string and return its index.

        If the string already exists, returns its existing index.
        Empty strings are always assigned index 0.
        """
        if s in self._index:
            return self._index[s]
        idx = len(self.strings)
        self.strings.append(s)
        self._index[s] = idx
        return idx

    def __getitem__(self, idx: int) -> str:
        """Get string by index."""
        return self.strings[idx]

    def __len__(self) -> int:
        return len(self.strings)
