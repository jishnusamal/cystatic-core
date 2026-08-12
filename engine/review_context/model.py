"""ReviewContext models — the public ABI of Factor.

Every dataclass is frozen (immutable) and contains only engineering concepts.
No presentation metadata, no scores, no ranking vectors, no rendering hints.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Change — hierarchical, file-centered structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChangeSummary:
    """High-level deterministic facts about the change.

    These values are derived from existing compiler outputs.
    No new computation.
    """
    classification: str = ""
    scope: str = ""
    file_count: int = 0
    symbol_count: int = 0
    behavior_count: int = 0


@dataclass(frozen=True)
class SymbolRef:
    """A reference to a changed symbol.

    Populated from existing symbol metadata.
    No invented metadata.
    """
    id: str = ""
    name: str = ""
    kind: str = ""
    visibility: str = ""
    language: str = ""
    location: str = ""


@dataclass(frozen=True)
class Change:
    """A single changed symbol within a file.

    Assembled from existing compiler artifacts.
    No new discovery.
    """
    symbol: SymbolRef = field(default_factory=SymbolRef)
    change_type: str = ""  # "added", "removed", "modified"
    behavior_changes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FileChange:
    """A file that was changed, with its changed symbols.

    The file is the primary review unit.
    """
    path: str = ""
    language: str = ""
    change_type: str = ""  # "added", "removed", "modified", "mixed"
    changes: tuple[Change, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ChangeContext:
    """Describe what changed.

    Organized hierarchically around files.
    No compiler-oriented flat lists.
    """
    summary: ChangeSummary = field(default_factory=ChangeSummary)
    files: tuple[FileChange, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Execution — hierarchical execution graph
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SymbolReference:
    """A reference to a repository symbol in an execution step.

    Must include enough metadata for downstream consumers.
    Reuses existing RepositoryModel metadata.
    """
    id: str = ""
    name: str = ""
    kind: str = ""
    location: str = ""


@dataclass(frozen=True)
class ReachedComponents:
    """Components reached by an execution step.

    Describes what service, module, or package this step reaches.
    Populated from existing compiler metadata — no new computation.
    """
    service: str = ""
    module: str = ""
    package: str = ""


@dataclass(frozen=True)
class ExecutionStep:
    """A single step in an execution chain.

    Represents one execution unit within a behavior's execution flow.
    Every field comes from existing compiler outputs — no new computation.

    Attributes:
        behavior: Behavior identifier (e.g., "behavior://...").
        symbol: Repository symbol corresponding to the behavior.
        kind: Repository symbol kind (function, method, endpoint, etc.).
        depth: Execution depth from the originating entry point.
        changed: True if the symbol exists in the ChangeModel.
        shared: True if this step participates in shared execution.
        reaches: Components (service, module, package) reached by this step.
        references: Compiler references backing this execution step.
    """
    behavior: str = ""
    symbol: SymbolReference = field(default_factory=SymbolReference)
    kind: str = ""
    depth: int = 0
    changed: bool = False
    shared: bool = False
    reaches: ReachedComponents = field(default_factory=ReachedComponents)
    references: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EntryPointExecution:
    """An entry point with its full execution chain.

    Organizes everything needed to understand execution starting from
    this entry point into a single navigable structure.
    Replaces the old flat collections (execution_chains, reachable_units,
    terminal_points, shared_execution).

    Attributes:
        endpoint: Name or identifier of the endpoint.
        method: HTTP method or trigger type (POST, GET, worker, etc.).
        path: Route path or trigger identifier.
        execution_chain: Ordered sequence of execution steps.
        terminal: Terminal point kind for this behavior.
        max_depth: Maximum execution depth from this entry point.
        references: Compiler references backing this entry point.
    """
    endpoint: str = ""
    method: str = ""
    path: str = ""
    execution_chain: tuple[ExecutionStep, ...] = field(default_factory=tuple)
    terminal: str = ""
    max_depth: int = 0
    references: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DeepestExecution:
    """The deepest execution path across all entry points.

    Eliminates the need for downstream consumers to search every
    entry point for the maximum depth.
    Reuses existing execution metrics — no recomputation.

    Attributes:
        entry_point: The entry point with the deepest execution.
        depth: The maximum execution depth.
        references: Compiler references.
    """
    entry_point: str = ""
    depth: int = 0
    references: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExecutionContext:
    """Describe where the change can execute.

    Organized hierarchically around entry points.
    Each entry point contains its own execution chain with
    per-step metadata (changed, shared, symbol info, reached components).

    These values already exist in Behavior and Discovery outputs.
    Reused — never recomputed.
    """
    entry_points: tuple[EntryPointExecution, ...] = field(default_factory=tuple)
    deepest_execution: DeepestExecution = field(default_factory=DeepestExecution)


# ---------------------------------------------------------------------------
# Reference (replaces "Evidence")
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Reference:
    """Traceability back to compiler artifacts.

    References are traceability only — no presentation metadata.
    """
    id: str = ""
    kind: str = ""
    location: str = ""
    compiler_artifact: str = ""
    supporting_nodes: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Discovery:
    """A single deterministic engineering discovery.

    Exposes the DiscoveryModel as a stable ABI.
    No ranking vectors, no scores, no rendering metadata, no presentation fields.

    Attributes:
        id: Stable identifier for this discovery.
        kind: Discovery type (e.g., "shared_execution", "deep_execution").
        statement: Deprecated — kept for backward compatibility.
        facts: Structured deterministic data for this discovery.
        reference_count: Total number of supporting references discovered (before truncation).
        references: Representative subset of references (at most MAX_DISCOVERY_REFERENCES).
    """
    id: str = ""
    kind: str = ""
    statement: str = ""  # Deprecated: kept for backward compatibility
    facts: dict[str, Any] = field(default_factory=dict)  # Structured deterministic data
    reference_count: int = 0
    references: tuple[Reference, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# ReviewContext — the final contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReviewContext:
    """The public ABI of Factor.

    Everything after ReviewContext is replaceable.
    No downstream consumer should need access to internal compiler models.

    Each section owns a single, well-defined purpose:
        change: What was modified (files, symbols, behavior changes).
        execution: How those modifications can execute (entry points, traces).
        discoveries: Deterministic conclusions a reviewer would care about.

    Each section owns its own supporting evidence — there is no global
    references collection. Discoveries contain their own references,
    execution contains its own evidence, etc.
    """
    change: ChangeContext = field(default_factory=ChangeContext)
    execution: ExecutionContext = field(default_factory=ExecutionContext)
    discoveries: tuple[Discovery, ...] = field(default_factory=tuple)