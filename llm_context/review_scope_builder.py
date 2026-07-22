"""Review Scope Builder

Provides a deterministic projection of a ReviewContext containing only the
artifacts required for review-scoped reasoning.

The builder consumes an already-materialized ReviewContext. It does NOT perform
static analysis or repository traversal. It filters the context to retain:

- changed files and symbols
- changed behaviors
- execution chains reachable from changed behaviors
- affected APIs, events, persistence entities, integrations
- validation relationships
- compiler discoveries with their supporting evidence
"""
from __future__ import annotations

import sys
from typing import Any

from review_context.model import (
    ReviewContext,
    ExecutionContext,
    EntryPointExecution,
    ExecutionStep,
    DeepestExecution,
    Discovery,
    Reference,
)

# ---------------------------------------------------------------------------
# Semantic Classification & Pruning helpers
# ---------------------------------------------------------------------------

LANGUAGE_PRIMITIVES = {
    "str", "int", "float", "bool", "dict", "list", "set", "tuple", "bytes",
    "Any", "Literal", "Optional", "Union", "TypeVar", "Generic", "Protocol", "UUID",
    "None", "object", "type", "frozenset", "bytearray", "complex",
}

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
    """Check if a string represents internal compiler metadata or graph IDs.

    Pruned identifiers (per review-scope spec):
      - ``unit://``  — compiler unit references
      - ``ref://``   — compiler traceability references (never consumed by the LLM)
      - ``node://``  — graph node identifiers
      - ``edge://``  — graph edge identifiers
      - strings containing ``graph`` — internal graph identifiers
      - hex strings of length >= 32 — internal hashes
    """
    if not val:
        return False
    val_lower = val.lower()
    if (
        val_lower.startswith("unit://") or
        val_lower.startswith("ref://") or
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
                is_changed = step.changed or (step.symbol and step.symbol.id in changed_symbols)

                sym_name = step.symbol.name if step.symbol else ""
                sym_id = step.symbol.id if step.symbol else ""
                sym_loc = step.symbol.location if step.symbol else ""
                sym_kind = step.symbol.kind if step.symbol else step.kind

                category = classify_symbol(sym_name, sym_id, sym_loc, sym_kind)

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

    # 3. Filter discoveries with evidence deduplication.
    # Identical Reference objects across multiple discoveries are canonicalized
    # to a single shared instance (keyed by id+kind+location+compiler_artifact).
    # This eliminates duplicate filtering work during serialization and reduces
    # memory pressure without changing the serialized format.
    seen_refs: dict[tuple[str, str, str, str], Reference] = {}
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
                    ref_key = (ref.id, ref.kind, ref.location, ref.compiler_artifact)
                    canonical = seen_refs.get(ref_key)
                    if canonical is None:
                        seen_refs[ref_key] = ref
                        canonical = ref
                    pruned_refs_list.append(canonical)

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


def build_review_scope(review_context: ReviewContext) -> ReviewContext:
    """Return a deterministic review-scoped projection of ``review_context``.

    Consumes the already-materialized ReviewContext and produces a minimal
    projection containing only artifacts required for review-scoped reasoning.
    No static analysis or repository traversal is performed.
    """
    return prune_review_context(review_context)
