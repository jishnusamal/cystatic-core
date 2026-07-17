"""Base classes for presentation compiler passes.

Every pass has:
- Input contract
- Output contract
- Transformation
- Algorithm
- Invariants
- Failure conditions
- Complexity
- What it must never do
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from operational.model import EngineeringDiscoveryModel
from presentation.model import (
    PresentationIR,
    PresentationDiscovery,
    PresentationEvidence,
    PresentationSummary,
    PresentationMetadata,
    PresentationNarrative,
    PresentationVisual,
    SignificanceMetrics,
    RankingVector,
    SurpriseVector,
    VisualSemantic,
    NarrativePosition,
    DiscoveryKind,
    NormalizedDiscovery,
)


@dataclass
class PresentationPassContext:
    """
    Mutable context passed between presentation compiler passes.

    Each pass reads from and writes to specific fields.
    The context accumulates state as passes execute.

    Input (set before first pass):
        discovery_model: EngineeringDiscoveryModel

    Pass 0 output:
        normalized_discoveries: list[NormalizedDiscovery]

    Pass 1 output:
        discoveries: list[PresentationDiscovery]

    Pass 2 output:
        significance_map: dict[str, SignificanceMetrics]

    Pass 3 output:
        ranked_discovery_ids: list[str]  (ordered by RankingVector)

    Pass 4 output:
        surprise_map: dict[str, SurpriseVector]

    Pass 5 output:
        compressed_groups: dict[str, list[str]]

    Pass 6 output:
        narrative_sections: list[PresentationNarrative]

    Pass 7 output:
        visuals: list[PresentationVisual]

    Pass 8 output:
        presentation_ir: PresentationIR | None
    """

    # Input: Engineering Discovery Model (immutable, set before first pass)
    discovery_model: EngineeringDiscoveryModel | None = None

    # Pass 0: Normalized discoveries from all compiler summaries
    normalized_discoveries: list[NormalizedDiscovery] = field(default_factory=list)

    # Pass 1: Extracted presentation discoveries
    discoveries: list[PresentationDiscovery] = field(default_factory=list)

    # Pass 2: Significance measurements per discovery
    significance_map: dict[str, SignificanceMetrics] = field(default_factory=dict)

    # Pass 3: Ranked discovery IDs in ORDER BY order
    ranked_discovery_ids: list[str] = field(default_factory=list)

    # Pass 4: Surprise vectors per discovery
    surprise_map: dict[str, SurpriseVector] = field(default_factory=dict)

    # Pass 5: Compressed discovery groups
    compressed_groups: dict[str, list[str]] = field(default_factory=dict)

    # Pass 6: Narrative sections
    narrative_sections: list[PresentationNarrative] = field(default_factory=list)

    # Pass 7: Visual semantics
    visuals: list[PresentationVisual] = field(default_factory=list)

    # Pass 8: Final Presentation IR
    presentation_ir: PresentationIR | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def discovery_count(self) -> int:
        """Get the total number of discoveries."""
        return len(self.discoveries)

    @property
    def evidence_count(self) -> int:
        """Get the total number of evidence references."""
        return sum(len(d.evidence) for d in self.discoveries)

    def get_discovery(self, discovery_id: str) -> PresentationDiscovery | None:
        """Get a discovery by its identifier."""
        for d in self.discoveries:
            if d.id == discovery_id:
                return d
        return None

    def get_discoveries_by_kind(self, kind: DiscoveryKind) -> list[PresentationDiscovery]:
        """Get all discoveries of a specific kind."""
        return [d for d in self.discoveries if d.kind == kind]

    def update_discovery(
        self,
        discovery_id: str,
        **kwargs: Any,
    ) -> None:
        """Update fields on a discovery in-place (replaces the dataclass instance)."""
        for i, d in enumerate(self.discoveries):
            if d.id == discovery_id:
                updates: dict[str, Any] = {
                    'id': d.id,
                    'kind': d.kind,
                    'title': d.title,
                    'summary': d.summary,
                    'evidence': d.evidence,
                    'metrics': d.metrics,
                    'ranking_vector': d.ranking_vector,
                    'surprise': d.surprise,
                    'visual_semantic': d.visual_semantic,
                    'narrative_position': d.narrative_position,
                    'compressed': d.compressed,
                    'children': d.children,
                    'source_artifact': d.source_artifact,
                    'metadata': d.metadata,
                }
                updates.update(kwargs)
                self.discoveries[i] = PresentationDiscovery(**updates)  # type: ignore[arg-type]
                return


class PresentationCompilationPass(ABC):
    """
    Base class for all presentation compiler passes.

    Each pass has a single responsibility and transforms the context
    for the next pass in the pipeline.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this pass."""
        pass

    @abstractmethod
    def run(self, context: PresentationPassContext) -> PresentationPassContext:
        """
        Execute the pass and return updated context.

        Args:
            context: The current pass context

        Returns:
            Updated pass context
        """
        pass

    def validate_input(self, context: PresentationPassContext) -> bool:
        """
        Validate that the context has required inputs for this pass.

        Override in subclasses to add validation logic.
        """
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"