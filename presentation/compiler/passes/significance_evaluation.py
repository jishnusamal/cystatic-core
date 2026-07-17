"""Pass 2 — Significance Evaluation.

Responsibility:
    Measure significance attributes for every discovery.
    Not importance — those are different. Importance belongs to ranking.

Input Contract:
    context.discoveries: list[PresentationDiscovery]
    context.discovery_model: EngineeringDiscoveryModel

Output Contract:
    context.significance_map: dict[str, SignificanceMetrics]
        Every discovery ID maps to its SignificanceMetrics.
        SignificanceMetrics contains only raw measurements — no scores, no weights.

Transformation:
    For each discovery, compute:
        execution_reach: How many execution paths / behaviors are affected.
        fan_out: Number of downstream consumers (callers, dependents, subscribers).
        propagation_depth: How far execution travels from entry to terminal.
        boundary_crossings: Number of architectural boundaries crossed.
        sharedness: Number of incoming references / dependents / consumers.
        external_surface: Number of external endpoints affected.
        data_surface: Number of data entities / tables / collections affected.
        validation_gap: Ratio (0.0-1.0) of uncovered execution paths.
        evidence_density: Number of independent evidence objects.
        cross_domain_evidence: Number of evidence sources from different compiler stages.

Algorithm:
    For each discovery:
        metrics = SignificanceMetrics()
        metrics.evidence_density = len(discovery.evidence)
        metrics.cross_domain_evidence = count unique evidence sources

        Switch on discovery.kind:
            ADDED_SYMBOLS, REMOVED_SYMBOLS, MODIFIED_SYMBOLS:
                metrics.execution_reach = count from behavior model
                metrics.fan_out = count from shared_executions
            CHANGED_ENDPOINTS:
                metrics.external_surface = count
                metrics.execution_reach = count from behavior model
            EXECUTION_CHAIN, REACHABLE_UNITS:
                metrics.execution_reach = count
                metrics.propagation_depth = execution_depth
            ENTRY_POINT, TERMINAL_POINT:
                metrics.boundary_crossings = count
            SHARED_EXECUTION:
                metrics.sharedness = count
            API_SURFACE:
                metrics.external_surface = count
            DATA_SURFACE:
                metrics.data_surface = count
            VALIDATION_GAP:
                metrics.validation_gap = ratio
            VALIDATION_COVERAGE:
                metrics.validation_gap = 1.0 - ratio

Invariants:
    - Every discovery receives exactly one SignificanceMetrics entry.
    - Metrics are raw measurements — never normalized, never weighted, never scored.
    - No interpretation occurs — only deterministic computation from compiler outputs.

Failure Conditions:
    - If discovery_model is None, compute only evidence_density and cross_domain_evidence.
    - If a discovery kind has no specific measurement logic, compute only evidence-based metrics.

Complexity:
    O(N) where N = number of discoveries.

Must Never:
    - Compute a single "significance score" or "importance score".
    - Normalize, weight, or combine metrics into a single value.
    - Rank or order discoveries.
    - Access renderer-specific formats.
"""
from __future__ import annotations

from presentation.model import (
    PresentationDiscovery,
    SignificanceMetrics,
    DiscoveryKind,
)
from .base import PresentationPassContext, PresentationCompilationPass


class SignificanceEvaluationPass(PresentationCompilationPass):
    """
    Pass 2: Computes deterministic significance **measurements** for each discovery.

    These are raw measurements — not scores, not weights, not ranks.
    Every metric is directly computed from compiler outputs.
    """

    @property
    def name(self) -> str:
        return "significance_evaluation"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Compute significance measurements for all discoveries."""
        if not context.discoveries:
            return context

        significance_map: dict[str, SignificanceMetrics] = {}

        for discovery in context.discoveries:
            metrics = self._compute_measurements(discovery, context)
            significance_map[discovery.id] = metrics

            # Attach metrics to the discovery
            context.update_discovery(discovery.id, metrics=metrics)

        context.significance_map = significance_map
        return context

    def _compute_measurements(
        self,
        discovery: PresentationDiscovery,
        context: PresentationPassContext,
    ) -> SignificanceMetrics:
        """Compute significance measurements for a single discovery."""
        model = context.discovery_model

        # Base measurements: always computed
        evidence_density = len(discovery.evidence)
        cross_domain_evidence = self._count_cross_domain_evidence(discovery)

        # Kind-specific measurements
        kind = discovery.kind

        if kind == DiscoveryKind.ADDED_SYMBOLS:
            return self._measure_added_symbols(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.REMOVED_SYMBOLS:
            return self._measure_removed_symbols(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.MODIFIED_SYMBOLS:
            return self._measure_modified_symbols(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.CHANGED_ENDPOINTS:
            return self._measure_changed_endpoints(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.CHANGED_IMPORTS:
            return self._measure_changed_imports(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.EXECUTION_CHAIN:
            return self._measure_execution_chain(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.REACHABLE_UNITS:
            return self._measure_reachable_units(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.EXECUTION_DEPTH:
            return self._measure_execution_depth(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.BEHAVIOR:
            return self._measure_behavior(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.ENTRY_POINT:
            return self._measure_entry_point(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.TERMINAL_POINT:
            return self._measure_terminal_point(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.SHARED_EXECUTION:
            return self._measure_shared_execution(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.API_SURFACE:
            return self._measure_api_surface(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.DATA_SURFACE:
            return self._measure_data_surface(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.EVENT_SURFACE:
            return self._measure_event_surface(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.DEPENDENCY_SURFACE:
            return self._measure_dependency_surface(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.VALIDATION_COVERAGE:
            return self._measure_validation_coverage(discovery, model, evidence_density, cross_domain_evidence)
        elif kind == DiscoveryKind.VALIDATION_GAP:
            return self._measure_validation_gap(discovery, model, evidence_density, cross_domain_evidence)
        else:
            # Default: evidence-only measurements
            return SignificanceMetrics(
                evidence_density=evidence_density,
                cross_domain_evidence=cross_domain_evidence,
            )

    # --- Kind-specific measurement methods ---

    def _measure_added_symbols(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of added symbols."""
        execution_reach = self._get_behavior_count(model)
        fan_out = self._get_shared_execution_count(model)
        return SignificanceMetrics(
            execution_reach=execution_reach,
            fan_out=fan_out,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_removed_symbols(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of removed symbols."""
        execution_reach = self._get_behavior_count(model)
        return SignificanceMetrics(
            execution_reach=execution_reach,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_modified_symbols(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of modified symbols."""
        execution_reach = self._get_behavior_count(model)
        fan_out = self._get_shared_execution_count(model)
        return SignificanceMetrics(
            execution_reach=execution_reach,
            fan_out=fan_out,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_changed_endpoints(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of changed endpoints."""
        external_surface = evidence_density  # Each evidence = one endpoint
        execution_reach = self._get_behavior_count(model)
        return SignificanceMetrics(
            execution_reach=execution_reach,
            external_surface=external_surface,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_changed_imports(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of changed imports."""
        return SignificanceMetrics(
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_execution_chain(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of execution chains."""
        execution_reach = evidence_density  # Each evidence = one chain
        propagation_depth = self._get_execution_depth(model)
        return SignificanceMetrics(
            execution_reach=execution_reach,
            propagation_depth=propagation_depth,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_reachable_units(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of reachable units."""
        execution_reach = evidence_density
        return SignificanceMetrics(
            execution_reach=execution_reach,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_execution_depth(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of execution depth."""
        propagation_depth = self._get_execution_depth(model)
        return SignificanceMetrics(
            propagation_depth=propagation_depth,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_behavior(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of a behavior."""
        execution_reach = 1  # One behavior
        propagation_depth = self._get_execution_depth(model)
        boundary_crossings = self._get_boundary_crossings(model)
        return SignificanceMetrics(
            execution_reach=execution_reach,
            propagation_depth=propagation_depth,
            boundary_crossings=boundary_crossings,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_entry_point(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of an entry point."""
        boundary_crossings = 1  # Entry point is a boundary
        return SignificanceMetrics(
            boundary_crossings=boundary_crossings,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_terminal_point(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of a terminal point."""
        boundary_crossings = 1  # Terminal point is a boundary
        return SignificanceMetrics(
            boundary_crossings=boundary_crossings,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_shared_execution(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of shared execution."""
        sharedness = evidence_density
        return SignificanceMetrics(
            sharedness=sharedness,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_api_surface(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of API surface."""
        external_surface = self._get_api_count(model)
        return SignificanceMetrics(
            external_surface=external_surface,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_data_surface(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of data surface."""
        data_surface = self._get_data_count(model)
        return SignificanceMetrics(
            data_surface=data_surface,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_event_surface(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of event surface."""
        return SignificanceMetrics(
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_dependency_surface(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of dependency surface."""
        return SignificanceMetrics(
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_validation_coverage(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of validation coverage."""
        # validation_gap = 0.0 means fully covered
        return SignificanceMetrics(
            validation_gap=0.0,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    def _measure_validation_gap(
        self,
        discovery: PresentationDiscovery,
        model: object,
        evidence_density: int,
        cross_domain_evidence: int,
    ) -> SignificanceMetrics:
        """Measure significance of validation gap."""
        # validation_gap = 1.0 means fully uncovered
        return SignificanceMetrics(
            validation_gap=1.0,
            evidence_density=evidence_density,
            cross_domain_evidence=cross_domain_evidence,
        )

    # --- Helpers ---

    def _count_cross_domain_evidence(self, discovery: PresentationDiscovery) -> int:
        """Count unique evidence sources across different compiler stages."""
        sources = set()
        for ev in discovery.evidence:
            sources.add(ev.source)
        return len(sources)

    def _get_behavior_count(self, model: object) -> int:
        """Get the number of behaviors from the model."""
        if model is None:
            return 0
        behavior = getattr(model, 'behavior', None)
        if behavior is None:
            return 0
        behaviors = getattr(behavior, 'behaviors', ())
        return len(behaviors)

    def _get_shared_execution_count(self, model: object) -> int:
        """Get the number of shared executions from the model."""
        if model is None:
            return 0
        shared = getattr(model, 'shared_executions', ())
        return len(shared)

    def _get_execution_depth(self, model: object) -> int:
        """Get the execution depth from the model."""
        if model is None:
            return 0
        return getattr(model, 'execution_depth', 0)

    def _get_boundary_crossings(self, model: object) -> int:
        """Get the number of boundary crossings from the model."""
        if model is None:
            return 0
        count = 0
        behavior = getattr(model, 'behavior', None)
        if behavior:
            count += len(getattr(behavior, 'entry_points', ()))
            count += len(getattr(behavior, 'terminal_points', ()))
        return count

    def _get_api_count(self, model: object) -> int:
        """Get the number of API endpoints from the model."""
        if model is None:
            return 0
        api = getattr(model, 'api', None)
        if api is None:
            return 0
        if hasattr(api, 'endpoints'):
            return len(api.endpoints)
        if hasattr(api, 'routes'):
            return len(api.routes)
        return 0

    def _get_data_count(self, model: object) -> int:
        """Get the number of data entities from the model."""
        if model is None:
            return 0
        data = getattr(model, 'data', None)
        if data is None:
            return 0
        for attr_name in ('entities', 'tables', 'collections'):
            if hasattr(data, attr_name):
                return len(getattr(data, attr_name))
        return 0