"""Discovery Compiler — orchestrates discovery compilation passes.

Consumes the EngineeringDiscoveryModel and produces DiscoveryIR.

The Discovery Compiler performs deterministic engineering discovery.
It never generates prose — only structured Discovery objects with
complete natural-language statements backed by evidence.

Pass pipeline:
    1. HiddenRelationshipPass: Reveal non-obvious relationships
    2. DominantExecutionPass: Identify symbols with greatest execution reach
    3. BoundaryInvariantPass: Highlight unchanged boundaries
    4. ValidationGapPass: Express missing validation in execution terms
    5. SharedExecutionPass: Convert existing shared execution data to discoveries

Every pass:
    - Reads from EngineeringDiscoveryModel (pre-computed compiler outputs)
    - Emits Discovery objects with complete statements
    - Never performs duplicate graph traversal
    - Is independently testable
"""

from __future__ import annotations

from datetime import datetime, timezone

from engine.operational.model import EngineeringDiscoveryModel
from engine.operational.discovery.model import (
    DiscoveryIR,
    Discovery,
    DiscoveryMetadata,
    DiscoverySummary,
    DiscoveryEvidence,
)
from engine.operational.discovery.passes.base import (
    DiscoveryPassContext,
    DiscoveryCompilerPass,
)
from engine.operational.discovery.passes.hidden_relationship import (
    HiddenRelationshipPass,
)
from engine.operational.discovery.passes.dominant_execution import DominantExecutionPass
from engine.operational.discovery.passes.boundary_invariant import BoundaryInvariantPass
from engine.operational.discovery.passes.validation_gap import ValidationGapPass
from engine.operational.discovery.passes.shared_execution import SharedExecutionPass
from engine.operational.discovery.passes.significance import SignificanceEvaluationPass
from engine.operational.discovery.passes.ranking import RankingPass
from engine.operational.discovery.passes.surprise import SurpriseDetectionPass
from engine.operational.discovery.passes.compression import CompressionPass


class DiscoveryCompiler:
    """Compiles an EngineeringDiscoveryModel into DiscoveryIR.

    This is the deterministic engineering discovery stage.
    It answers questions that normally require manual investigation.

    The compiler is stateless and deterministic. Same inputs always produce
    the same DiscoveryIR.

    Input: EngineeringDiscoveryModel
    Output: DiscoveryIR
    """

    COMPILER_VERSION: str = "1.0.0"

    def __init__(self) -> None:
        """Initialize the compiler with all discovery passes."""
        self.passes: list[DiscoveryCompilerPass] = [
            HiddenRelationshipPass(),  # Pass 1  - Non-obvious relationships
            DominantExecutionPass(),  # Pass 2  - Greatest execution reach
            BoundaryInvariantPass(),  # Pass 3  - Unchanged boundaries
            ValidationGapPass(),  # Pass 4  - Missing validation
            SharedExecutionPass(),  # Pass 5  - Shared infrastructure
            SignificanceEvaluationPass(),  # Pass 6  [MOVED] - Measurements
            RankingPass(),  # Pass 7  [MOVED] - Lexicographic ORDER BY
            SurpriseDetectionPass(),  # Pass 8  [MOVED] - Ratio vectors
            CompressionPass(),  # Pass 9  [MOVED] - Group related
        ]

    def compile(
        self,
        discovery_model: EngineeringDiscoveryModel,
    ) -> DiscoveryIR:
        """Compile an EngineeringDiscoveryModel into DiscoveryIR.

        Args:
            discovery_model: The EngineeringDiscoveryModel to analyze.

        Returns:
            DiscoveryIR containing all deterministic discoveries.

        Raises:
            ValueError: If discovery_model is None.
        """
        if discovery_model is None:
            raise ValueError("discovery_model is required")

        # Initialize pass context
        context = DiscoveryPassContext(
            discovery_model=discovery_model,
        )

        # Execute each pass in sequence
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        # Build the final DiscoveryIR
        return self._build_discovery_ir(context)

    def _build_discovery_ir(self, context: DiscoveryPassContext) -> DiscoveryIR:
        """Build the final DiscoveryIR from the pass context.

        Args:
            context: Final pass context with all discoveries.

        Returns:
            Complete DiscoveryIR.
        """
        discoveries = context.discoveries

        # Sort by importance descending
        discoveries.sort(key=lambda d: d.importance, reverse=True)

        # Build evidence index
        evidence_index: dict[str, tuple[DiscoveryEvidence, ...]] = {}
        for d in discoveries:
            if d.evidence:
                evidence_index[d.id] = d.evidence

        # Count by kind
        kind_counts: dict[str, int] = {}
        for d in discoveries:
            kind_counts[d.kind.value] = kind_counts.get(d.kind.value, 0) + 1

        # Build summary
        highest_importance = max((d.importance for d in discoveries), default=0.0)
        summary = DiscoverySummary(
            total_discoveries=len(discoveries),
            hidden_relationships=kind_counts.get("hidden_relationship", 0),
            dominant_executions=kind_counts.get("dominant_execution", 0)
            + kind_counts.get("fan_in", 0)
            + kind_counts.get("fan_out", 0)
            + kind_counts.get("execution_depth", 0),
            boundary_invariants=kind_counts.get("boundary_invariant", 0),
            validation_gaps=kind_counts.get("validation_gap", 0),
            shared_executions=kind_counts.get("shared_execution", 0),
            cross_service=kind_counts.get("cross_service", 0),
            compressed_groups=kind_counts.get("compressed", 0),
            highest_importance=highest_importance,
        )

        # Count total evidence
        total_evidence = sum(len(d.evidence) for d in discoveries)

        # Build metadata
        metadata = DiscoveryMetadata(
            compiler_version=self.COMPILER_VERSION,
            compiled_at=datetime.now(timezone.utc).isoformat(),
            discovery_count=len(discoveries),
            evidence_count=total_evidence,
            pass_count=len(self.passes),
        )

        return DiscoveryIR(
            metadata=metadata,
            discoveries=tuple(discoveries),
            summary=summary,
            evidence_index=evidence_index,
        )

    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]
