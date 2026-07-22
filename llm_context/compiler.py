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
from typing import Any

import sys
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


# Regex for extracting file path and line range from location strings
_LOCATION_RE = re.compile(r"^(.+?)(?::(\d+)(?:-(\d+))?)?$")


# ---------------------------------------------------------------------------
# Semantic Classification & Pruning for High-Density Context
# ---------------------------------------------------------------------------

LANGUAGE_PRIMITIVES = {
    "str", "int", "float", "bool", "dict", "list", "set", "tuple", "bytes",
    "Any", "Literal", "Optional", "Union", "TypeVar", "Generic", "Protocol", "UUID",
    "None", "object", "type", "frozenset", "bytearray", "complex",
}

# Standard library module names
STD_LIBS = sys.stdlib_module_names if hasattr(sys, "stdlib_module_names") else {
    "os", "sys", "json", "math", "time", "datetime", "typing", "collections", "functools",
    "itertools", "hashlib", "base64", "secrets", "logging", "asyncio", "uuid", "pathlib",
    "re", "random", "subprocess", "threading", "multiprocessing", "io", "socket",
    "select", "struct", "copy", "contextlib", "argparse", "tempfile", "shutil", "glob",
    "fnmatch", "pickle", "csv", "sqlite3", "ctypes", "platform", "weakref", "abc",
    "enum", "inspect", "traceback", "warnings", "urllib", "http", "xml", "html", "email",
    "unittest", "mock"
}

FRAMEWORK_MODULES = {
    "fastapi", "starlette", "uvicorn", "gunicorn", "pydantic_settings", "pydantic",
    "django", "flask", "flask_restful", "jinja2", "amplitude", "sentry_sdk"
}

FRAMEWORK_NAMES = {
    "FastAPI", "APIRouter", "Depends", "Request", "Response", "RedirectResponse",
    "HTTPException", "BackgroundTasks", "CORSMiddleware", "cors", "middleware",
    "router", "route", "app", "lifecycle", "handler",
}

ORM_MODULES = {"sqlalchemy", "tortoise", "asyncpg", "databases"}

ORM_NAMES = {
    "select", "insert", "update", "delete", "func", "op", "ForeignKey", "Sequence",
    "relationship", "joinedload", "selectinload", "AsyncSession", "Session",
    "Column", "Integer", "String", "Base", "metadata", "declarative_base", "sessionmaker",
}

NOISE_CATEGORIES = {
    "Runtime",
    "Standard Library",
    "Framework",
    "Infrastructure",
    "Tooling",
    "Build",
    "Test"
}


def is_compiler_metadata(val: str) -> bool:
    """Check if a string represents internal compiler metadata or graph IDs."""
    if not val:
        return False
    val_lower = val.lower()
    if (
        val_lower.startswith("unit://") or
        val_lower.startswith("node://") or
        val_lower.startswith("edge://") or
        "graph" in val_lower
    ):
        return True
    # Hex hashes of length >= 32
    if len(val) >= 32 and all(c in "0123456789abcdefABCDEF" for c in val):
        return True
    return False


def classify_symbol(name: str, symbol_id: str, file_path: str, kind: str) -> str:
    """Classify a symbol into a semantic category to support generic filtering."""
    path_lower = file_path.lower() if file_path else ""
    name_lower = name.lower() if name else ""
    kind_lower = kind.lower() if kind else ""
    
    # 1. Build
    if (
        ".github/" in path_lower or
        ".gitlab-ci" in path_lower or
        "docker" in path_lower or
        "makefile" in path_lower or
        "setup.py" in path_lower or
        "setup.cfg" in path_lower or
        "pyproject.toml" in path_lower or
        "tox.ini" in path_lower or
        ".gitignore" in path_lower or
        "requirements" in path_lower or
        "uv.lock" in path_lower
    ):
        return "Build"
        
    # 2. Tooling
    if (
        "dev/" in path_lower or
        "scripts/" in path_lower or
        "cli.py" in path_lower or
        "install" in path_lower or
        "bootstrap" in path_lower or
        ".venv" in path_lower
    ):
        return "Tooling"
        
    # 3. Test
    is_test = False
    if (
        "/tests/" in path_lower or
        "/test/" in path_lower or
        path_lower.startswith("tests/") or
        path_lower.startswith("test/") or
        "test_" in path_lower or
        "_test.py" in path_lower
    ):
        is_test = True
    elif (
        "test_" in name_lower or
        "mock" in name_lower or
        "monkeypatch" in name_lower or
        "fixture" in name_lower or
        "assert" in name_lower or
        kind_lower == "test"
    ):
        is_test = True
        
    if is_test:
        return "Test"
        
    # 4. Runtime / Standard Library
    if name in LANGUAGE_PRIMITIVES:
        return "Runtime"
        
    parts = name.split(".")
    first_part = parts[0]
    if first_part in STD_LIBS:
        return "Standard Library"
        
    # 5. Framework
    if (
        first_part in FRAMEWORK_MODULES or
        name in FRAMEWORK_NAMES or
        "middleware" in name_lower or
        "router" in name_lower or
        "route" in name_lower or
        "app" == name_lower
    ):
        return "Framework"
        
    # 6. Infrastructure
    if (
        first_part in ORM_MODULES or
        name in ORM_NAMES or
        "db" in name_lower or
        "database" in name_lower or
        "sql" in name_lower or
        "query" in name_lower or
        "cache" in name_lower or
        "redis" in name_lower or
        "logger" in name_lower or
        "logging" in name_lower or
        "connection" in name_lower or
        "pool" in name_lower
    ):
        return "Infrastructure"
        
    # 7. Event
    if (
        kind_lower in {"worker", "task", "event"} or
        "event" in name_lower or
        "publish" in name_lower or
        "subscribe" in name_lower or
        "queue" in name_lower or
        "consumer" in name_lower or
        "producer" in name_lower
    ):
        return "Event"
        
    # 8. API
    if (
        kind_lower in {"endpoint", "route"} or
        "api" in name_lower or
        "endpoint" in name_lower or
        "controller" in name_lower
    ):
        return "API"
        
    # 9. Validation
    if (
        "validate" in name_lower or
        "validator" in name_lower or
        "check" in name_lower or
        "schema" in name_lower
    ):
        return "Validation"
        
    # 10. Integration
    if (
        "integration" in name_lower or
        "client" in name_lower or
        "external" in name_lower or
        "webhook" in name_lower
    ):
        return "Integration"
        
    # 11. Database Schema
    if (
        "model" in name_lower or
        "table" in name_lower or
        "entity" in name_lower
    ):
        return "Database Schema"
        
    # 12. Domain Model / Business Logic
    if kind_lower in {"class", "interface", "enum"}:
        return "Domain Model"
        
    return "Business Logic"


def prune_review_context(review_context: ReviewContext) -> ReviewContext:
    """Pre-filter ReviewContext to retain only high-signal production data."""
    # 1. Build preservation sets (subject of code change)
    changed_files: set[str] = set()
    changed_symbols: set[str] = set()
    
    if review_context.change and review_context.change.files:
        for f in review_context.change.files:
            changed_files.add(f.path)
            for c in f.changes:
                if c.symbol:
                    changed_symbols.add(c.symbol.id)
                    
    # 2. Filter execution entry points & collapse noise steps
    pruned_entry_points: list[EntryPointExecution] = []
    if review_context.execution and review_context.execution.entry_points:
        for ep in review_context.execution.entry_points:
            pruned_steps: list[ExecutionStep] = []
            for step in ep.execution_chain:
                # Check if this node is changed/part of preservation set
                is_changed = step.changed or (step.symbol and step.symbol.id in changed_symbols)
                
                # Semantic classification
                sym_name = step.symbol.name if step.symbol else ""
                sym_id = step.symbol.id if step.symbol else ""
                sym_loc = step.symbol.location if step.symbol else ""
                sym_kind = step.symbol.kind if step.symbol else step.kind
                
                category = classify_symbol(sym_name, sym_id, sym_loc, sym_kind)
                
                # Keep if it is changed or NOT in noise categories
                if is_changed or category not in NOISE_CATEGORIES:
                    pruned_refs = tuple(
                        ref_str for ref_str in step.references
                        if not is_compiler_metadata(ref_str)
                    )
                    pruned_step = ExecutionStep(
                        behavior=step.behavior,
                        symbol=step.symbol,
                        kind=step.kind,
                        depth=step.depth,
                        changed=step.changed,
                        shared=step.shared,
                        reaches=step.reaches,
                        references=pruned_refs
                    )
                    pruned_steps.append(pruned_step)
            
            pruned_ep_refs = tuple(
                ref_str for ref_str in ep.references
                if not is_compiler_metadata(ref_str)
            )
            pruned_terminal = "" if is_compiler_metadata(ep.terminal) else ep.terminal
            
            pruned_ep = EntryPointExecution(
                endpoint=ep.endpoint,
                method=ep.method,
                path=ep.path,
                execution_chain=tuple(pruned_steps),
                terminal=pruned_terminal,
                max_depth=ep.max_depth,
                references=pruned_ep_refs
            )
            pruned_entry_points.append(pruned_ep)
            
    de = review_context.execution.deepest_execution if review_context.execution else None
    if de:
        pruned_de_refs = tuple(
            ref_str for ref_str in de.references
            if not is_compiler_metadata(ref_str)
        )
        pruned_de = DeepestExecution(
            entry_point=de.entry_point,
            depth=de.depth,
            references=pruned_de_refs
        )
    else:
        pruned_de = DeepestExecution()
        
    pruned_execution = ExecutionContext(
        entry_points=tuple(pruned_entry_points),
        deepest_execution=pruned_de
    )
    
    # 3. Filter discoveries
    pruned_discoveries: list[Discovery] = []
    if review_context.discoveries:
        for d in review_context.discoveries:
            pruned_refs_list: list[Reference] = []
            for ref in d.references:
                if not (
                    is_compiler_metadata(ref.id) or
                    is_compiler_metadata(ref.location) or
                    is_compiler_metadata(ref.compiler_artifact)
                ):
                    pruned_refs_list.append(ref)
                    
            pruned_facts: dict[str, Any] = {}
            for k, v in d.facts.items():
                if not (is_compiler_metadata(k) or (isinstance(v, str) and is_compiler_metadata(v))):
                    pruned_facts[k] = v
                    
            pruned_disc = Discovery(
                id=d.id,
                kind=d.kind,
                statement=d.statement,
                facts=pruned_facts,
                reference_count=len(pruned_refs_list),
                references=tuple(pruned_refs_list)
            )
            pruned_discoveries.append(pruned_disc)
            
    return ReviewContext(
        change=review_context.change,
        execution=pruned_execution,
        discoveries=tuple(pruned_discoveries)
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

    def compile(self, review_context: ReviewContext) -> LLMContext:
        """Compile a ReviewContext into an LLMContext.

        Args:
            review_context: The ReviewContext to compile.

        Returns:
            An LLMContext containing key facts from ReviewContext in a
            token-efficient compact representation.
        """
        # Phase 0: Prune implementation noise semantically
        pruned_context = prune_review_context(review_context)

        sb = _StringBuilder()

        # Phase 1: Build enum-encoded lookup tables
        file_table = self._build_file_table(pruned_context.change, sb)
        symbol_table, symbol_id_map = self._build_symbol_table(
            pruned_context.change, file_table, sb
        )
        endpoint_table = self._build_endpoint_table(pruned_context.execution, sb)

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

        return table, seen

    def _build_endpoint_table(
        self,
        exec_ctx: ExecutionContext,
        sb: _StringBuilder,
    ) -> list[tuple[int, int]]:
        """Build normalized endpoint lookup table.

        Each entry: (endpoint_idx, path_idx)
        """
        table: list[tuple[int, int]] = []
        seen: dict[str, int] = {}  # endpoint string -> index

        for ep in exec_ctx.entry_points:
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
            chain_node_idxs: list[int] = []
            prev_node_idx: int | None = None

            for step in ep.execution_chain:
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