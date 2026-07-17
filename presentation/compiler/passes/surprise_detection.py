"""Pass 4 — Surprise Detection.

Responsibility:
    Identify surprising discoveries by computing deterministic ratios between
    observable change and system impact. Pure measurements — no risk labels.

Input Contract:
    context.discoveries: list[PresentationDiscovery] (ranked, with metrics)
    context.discovery_model: EngineeringDiscoveryModel

Output Contract:
    context.surprise_map: dict[str, SurpriseVector]
        Every discovery with ratio above threshold gets a SurpriseVector.
    Every surprising discovery has its surprise vector populated.

Transformation:
    For each discovery, compute component ratios:
        reach_ratio: execution_reach / changed_symbols
        propagation_ratio: propagation_depth / changed_files
        boundary_ratio: boundary_crossings / changed_symbols
        fan_out_ratio: fan_out / changed_endpoints
        service_ratio: services_reached / diff_size

    max_ratio = max(all component ratios)

Algorithm:
    for discovery in discoveries:
        metrics = significance_map[discovery.id]
        change_size = count changed symbols from model
        file_count = count changed files from model
        endpoint_count = count changed endpoints from model

        vector = SurpriseVector(
            reach_ratio=metrics.execution_reach / max(change_size, 1),
            propagation_ratio=metrics.propagation_depth / max(file_count, 1),
            boundary_ratio=metrics.boundary_crossings / max(change_size, 1),
            fan_out_ratio=metrics.fan_out / max(endpoint_count, 1),
            service_ratio=metrics.external_surface / max(file_count, 1),
            max_ratio=max(all ratios),
            description="..." if max_ratio > threshold
        )

        if vector.max_ratio >= MIN_SURPRISE_RATIO:
            surprise_map[discovery.id] = vector

Invariants:
    - Surprise is a vector of pure ratios — no AI, no heuristics.
    - Never labels discoveries as "risky", "dangerous", or "problematic".
    - Only identifies unexpected deterministic relationships.

Failure Conditions:
    - If no change data is available, skip ratio computation.
    - If denominator is zero, use 1 to avoid division by zero.

Complexity:
    O(N) where N = number of discoveries.

Must Never:
    - Use AI, heuristics, or risk assessment.
    - Label discoveries as risky, dangerous, or problematic.
    - Access renderer-specific formats.
"""
from __future__ import annotations

from presentation.model import (
    PresentationDiscovery,
    SurpriseVector,
    SignificanceMetrics,
)
from .base import PresentationPassContext, PresentationCompilationPass


class SurpriseDetectionPass(PresentationCompilationPass):
    """
    Pass 4: Detects deterministic surprises by comparing change size vs system impact.

    A surprise is a ratio between observable change and observed system impact.
    High ratio = high surprise. Pure deterministic measurement.
    """

    # Minimum ratio to flag a discovery as surprising
    MIN_SURPRISE_RATIO: float = 5.0

    @property
    def name(self) -> str:
        return "surprise_detection"

    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """Detect surprising discoveries by computing ratio vectors."""
        if not context.discoveries:
            return context

        surprise_map: dict[str, SurpriseVector] = {}
        model = context.discovery_model

        for discovery in context.discoveries:
            metrics = context.significance_map.get(discovery.id)
            if metrics is None:
                continue

            vector = self._compute_surprise_vector(discovery, metrics, model)
            if vector is not None and vector.max_ratio >= self.MIN_SURPRISE_RATIO:
                surprise_map[discovery.id] = vector
                context.update_discovery(discovery.id, surprise=vector)

        context.surprise_map = surprise_map
        return context

    def _compute_surprise_vector(
        self,
        discovery: PresentationDiscovery,
        metrics: SignificanceMetrics,
        model: object,
    ) -> SurpriseVector | None:
        """Compute SurpriseVector for a single discovery."""
        # Get change size denominators
        change_size = self._get_changed_symbol_count(model)
        file_count = self._get_changed_file_count(model)
        endpoint_count = self._get_changed_endpoint_count(model)

        # Avoid division by zero
        change_size = max(change_size, 1)
        file_count = max(file_count, 1)
        endpoint_count = max(endpoint_count, 1)

        # Compute component ratios
        reach_ratio = self._safe_ratio(metrics.execution_reach, change_size)
        propagation_ratio = self._safe_ratio(metrics.propagation_depth, file_count)
        boundary_ratio = self._safe_ratio(metrics.boundary_crossings, change_size)
        fan_out_ratio = self._safe_ratio(metrics.fan_out, endpoint_count)
        service_ratio = self._safe_ratio(metrics.external_surface, file_count)

        ratios = [reach_ratio, propagation_ratio, boundary_ratio, fan_out_ratio, service_ratio]
        max_ratio = max(ratios)

        if max_ratio < self.MIN_SURPRISE_RATIO:
            return None

        # Find the dominant ratio for the description
        dominant = self._find_dominant_ratio(
            reach_ratio, propagation_ratio, boundary_ratio,
            fan_out_ratio, service_ratio,
        )
        description = self._build_description(dominant, discovery)

        return SurpriseVector(
            reach_ratio=reach_ratio,
            propagation_ratio=propagation_ratio,
            boundary_ratio=boundary_ratio,
            fan_out_ratio=fan_out_ratio,
            service_ratio=service_ratio,
            max_ratio=round(max_ratio, 1),
            description=description,
        )

    def _get_changed_symbol_count(self, model: object) -> int:
        """Get the total number of changed symbols."""
        if model is None:
            return 0
        change = getattr(model, 'change', None)
        if change is None:
            return 0
        return (
            len(getattr(change, 'added_symbols', ()))
            + len(getattr(change, 'removed_symbols', ()))
            + len(getattr(change, 'modified_symbols', ()))
        )

    def _get_changed_file_count(self, model: object) -> int:
        """Get the number of changed files."""
        if model is None:
            return 0
        change = getattr(model, 'change', None)
        if change is None:
            return 0
        # Try to get changed_files if it exists
        files = getattr(change, 'changed_files', ())
        if files:
            return len(files)
        # Estimate from unique files in changed imports
        imports = getattr(change, 'changed_imports', ())
        if imports:
            files_set = set()
            for imp in imports:
                file = getattr(imp, 'file', None)
                if file:
                    files_set.add(file)
            return max(len(files_set), 1)
        return 1

    def _get_changed_endpoint_count(self, model: object) -> int:
        """Get the number of changed endpoints."""
        if model is None:
            return 0
        change = getattr(model, 'change', None)
        if change is None:
            return 0
        return len(getattr(change, 'changed_endpoints', ()))

    @staticmethod
    def _safe_ratio(numerator: int, denominator: int) -> float:
        """Compute a ratio safely."""
        if denominator == 0:
            return 0.0
        return round(numerator / denominator, 1)

    def _find_dominant_ratio(
        self,
        reach_ratio: float,
        propagation_ratio: float,
        boundary_ratio: float,
        fan_out_ratio: float,
        service_ratio: float,
    ) -> tuple[str, float]:
        """Find the dominant ratio and its label."""
        candidates = [
            ("reach", reach_ratio),
            ("propagation", propagation_ratio),
            ("boundary", boundary_ratio),
            ("fan_out", fan_out_ratio),
            ("service", service_ratio),
        ]
        # Find the maximum by ratio value, then by label alphabetically for stability
        candidates.sort(key=lambda x: (-x[1], x[0]))
        return candidates[0]

    def _build_description(
        self,
        dominant: tuple[str, float],
        discovery: PresentationDiscovery,
    ) -> str:
        """Build a human-readable description of the dominant surprise."""
        label_map = {
            "reach": "execution reach",
            "propagation": "propagation depth",
            "boundary": "boundary crossings",
            "fan_out": "downstream consumers",
            "service": "services reached",
        }
        label = label_map.get(dominant[0], "system impact")
        ratio = dominant[1]

        return (
            f"Surprising {label} ratio ({ratio}x): "
            f"{discovery.summary}"
        )