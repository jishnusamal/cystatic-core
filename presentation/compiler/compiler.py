"""Presentation Compiler — orchestrates compilation passes.

Transforms EngineeringDiscoveryModel into a stable PresentationIR
optimized for human understanding.

Pass pipeline:
    0. Normalization: Convert four compiler summaries into one canonical source
    1. Discovery Extraction: Convert normalized discoveries to PresentationDiscovery objects
    2. Significance Evaluation: Measure significance attributes (not scores)
    3. Ranking: Order by RankingVector (lexicographic ORDER BY)
    4. Surprise Detection: Compute ratio vectors (change size vs system impact)
    5. Compression: Group related discoveries without losing meaning
    6. Narrative Construction: Assign narrative positions (dependency ordering)
    7. Visual Composition: Assign semantic visuals (renderer chooses concrete format)
    8. IR Assembly: Assemble final stable intermediate representation

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

from operational.model import EngineeringDiscoveryModel
from presentation.model import PresentationIR

from .passes import (
    PresentationPassContext,
    NormalizationPass,
    DiscoveryExtractionPass,
    SignificanceEvaluationPass,
    RankingPass,
    SurpriseDetectionPass,
    CompressionPass,
    NarrativeConstructionPass,
    VisualCompositionPass,
    IRAssemblyPass,
)


class PresentationCompiler:
    """
    Compiles an EngineeringDiscoveryModel into a PresentationIR.

    This is the final compiler stage in the Factor pipeline. Its responsibility
    is to transform deterministic engineering discovery into a representation
    optimized for human understanding.

    The compiler is deterministic and stateless. Same inputs always produce
    the same PresentationIR.

    Input: EngineeringDiscoveryModel
    Output: PresentationIR
    """

    def __init__(self) -> None:
        """Initialize the compiler with all 9 passes."""
        self.passes = [
            NormalizationPass(),              # Pass 0
            DiscoveryExtractionPass(),         # Pass 1
            SignificanceEvaluationPass(),      # Pass 2
            RankingPass(),                     # Pass 3
            SurpriseDetectionPass(),           # Pass 4
            CompressionPass(),                 # Pass 5
            NarrativeConstructionPass(),       # Pass 6
            VisualCompositionPass(),           # Pass 7
            IRAssemblyPass(),                  # Pass 8
        ]

    def compile(
        self,
        discovery_model: EngineeringDiscoveryModel,
    ) -> PresentationIR:
        """
        Compile an EngineeringDiscoveryModel into a PresentationIR.

        Args:
            discovery_model: The EngineeringDiscoveryModel to compile.

        Returns:
            PresentationIR containing the structured presentation output.

        Raises:
            ValueError: If discovery_model is invalid.
            RuntimeError: If pipeline completes without producing IR.
        """
        if discovery_model is None:
            raise ValueError("discovery_model is required")

        # Initialize pass context with the engineering discovery model
        context = PresentationPassContext(
            discovery_model=discovery_model,
        )

        # Execute each pass in sequence
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        # Return the assembled PresentationIR
        ir = context.presentation_ir
        if ir is None:
            raise RuntimeError(
                "Presentation compiler pipeline completed but no "
                "PresentationIR was produced. This indicates a bug in "
                "the IR assembly pass."
            )
        return ir

    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]

    def compile_with_context(
        self,
        discovery_model: EngineeringDiscoveryModel,
    ) -> PresentationPassContext:
        """
        Compile and return the full pass context.

        This is useful for debugging and testing. It returns the full
        context after all passes have executed, which includes all
        intermediate state.

        Args:
            discovery_model: The EngineeringDiscoveryModel to compile.

        Returns:
            PresentationPassContext with all intermediate state.
        """
        if discovery_model is None:
            raise ValueError("discovery_model is required")

        context = PresentationPassContext(
            discovery_model=discovery_model,
        )

        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        return context