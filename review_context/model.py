"""ReviewContext models — the public ABI of Factor.

Every dataclass is frozen (immutable) and contains only engineering concepts.
No presentation metadata, no scores, no ranking vectors, no rendering hints.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# ChangeContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChangeContext:
    """Describe what changed.

    Only includes information required to understand the change.
    No compiler metadata, timing, or internal IDs.
    """
    changed_files: tuple[str, ...] = field(default_factory=tuple)
    changed_symbols: tuple[str, ...] = field(default_factory=tuple)
    changed_behaviors: tuple[str, ...] = field(default_factory=tuple)
    classification: str = ""
    scope: str = ""


# ---------------------------------------------------------------------------
# ExecutionContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionContext:
    """Describe where the change can execute.

    These values already exist in Behavior and Discovery outputs.
    Reused — never recomputed.
    """
    entry_points: tuple[str, ...] = field(default_factory=tuple)
    execution_chains: tuple[str, ...] = field(default_factory=tuple)
    terminal_points: tuple[str, ...] = field(default_factory=tuple)
    reachable_units: tuple[str, ...] = field(default_factory=tuple)
    shared_execution: tuple[str, ...] = field(default_factory=tuple)
    max_execution_depth: int = 0


# ---------------------------------------------------------------------------
# ImpactContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ImpactContext:
    """Describe everything affected.

    Only deterministic relationships. No scoring.
    """
    services: tuple[str, ...] = field(default_factory=tuple)
    modules: tuple[str, ...] = field(default_factory=tuple)
    callers: tuple[str, ...] = field(default_factory=tuple)
    dependents: tuple[str, ...] = field(default_factory=tuple)
    fan_in: int = 0
    fan_out: int = 0
    cross_service_references: tuple[str, ...] = field(default_factory=tuple)
    boundary_crossings: int = 0
    propagation: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# StateContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StateContext:
    """Describe data affected.

    Reuses Operational Compiler outputs.
    """
    models: tuple[str, ...] = field(default_factory=tuple)
    tables: tuple[str, ...] = field(default_factory=tuple)
    reads: tuple[str, ...] = field(default_factory=tuple)
    writes: tuple[str, ...] = field(default_factory=tuple)
    transactions: tuple[str, ...] = field(default_factory=tuple)
    caches: tuple[str, ...] = field(default_factory=tuple)
    external_storage: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# IntegrationContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntegrationContext:
    """Describe interactions outside local execution.

    Only expose facts. No summaries.
    """
    rest: tuple[str, ...] = field(default_factory=tuple)
    graphql: tuple[str, ...] = field(default_factory=tuple)
    rpc: tuple[str, ...] = field(default_factory=tuple)
    events: tuple[str, ...] = field(default_factory=tuple)
    queues: tuple[str, ...] = field(default_factory=tuple)
    workers: tuple[str, ...] = field(default_factory=tuple)
    async_chains: tuple[str, ...] = field(default_factory=tuple)
    external_systems: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# ValidationContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationContext:
    """Describe validation available.

    No recommendations.
    """
    unit_tests: tuple[str, ...] = field(default_factory=tuple)
    integration_tests: tuple[str, ...] = field(default_factory=tuple)
    e2e_tests: tuple[str, ...] = field(default_factory=tuple)
    benchmarks: tuple[str, ...] = field(default_factory=tuple)
    production_replays: tuple[str, ...] = field(default_factory=tuple)
    validation_gaps: tuple[str, ...] = field(default_factory=tuple)


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

    The statement is deterministic and references point back to compiler artifacts.
    No ranking vectors, no scores, no rendering metadata, no presentation fields.
    """
    id: str = ""
    kind: str = ""
    statement: str = ""
    references: tuple[Reference, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# ReviewContext — the final contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReviewContext:
    """The public ABI of Factor.

    Everything after ReviewContext is replaceable.
    No downstream consumer should need access to internal compiler models.

    Attributes:
        change: What changed.
        execution: Where the change can execute.
        impact: Everything affected.
        state: Data affected.
        integration: Interactions outside local execution.
        validation: Validation available.
        discoveries: Deterministic engineering discoveries.
        references: Traceability back to compiler artifacts.
    """
    change: ChangeContext = field(default_factory=ChangeContext)
    execution: ExecutionContext = field(default_factory=ExecutionContext)
    impact: ImpactContext = field(default_factory=ImpactContext)
    state: StateContext = field(default_factory=StateContext)
    integration: IntegrationContext = field(default_factory=IntegrationContext)
    validation: ValidationContext = field(default_factory=ValidationContext)
    discoveries: tuple[Discovery, ...] = field(default_factory=tuple)
    references: tuple[Reference, ...] = field(default_factory=tuple)