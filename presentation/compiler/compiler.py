"""Presentation Compiler — orchestrates compilation passes.

Transforms DiscoveryIR into a stable PresentationIR
optimized for human understanding.

The Discovery Compiler performs all deterministic analysis.
The Presentation Compiler only formats for humans.

Pass pipeline:
    0. Normalization: Convert DiscoveryIR into presentation-ready format
    1. Discovery Extraction: Convert Discovery objects to PresentationDiscovery objects
    2. Narrative Construction: Assign narrative positions (dependency ordering)
    3. Visual Composition: Assign semantic visuals (renderer chooses concrete format)
    4. IR Assembly: Assemble final stable intermediate representation

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

from operational.discovery.model import DiscoveryIR
from presentation.model import PresentationIR

from .passes import (
    PresentationPassContext,
    NormalizationPass,
    DiscoveryExtractionPass,
    NarrativeConstructionPass,
    VisualCompositionPass,
    IRAssemblyPass,
)


class PresentationCompiler:
    """
    Compiles a DiscoveryIR into a PresentationIR.

    This is the final compiler stage in the Factor pipeline. Its responsibility
    is to transform deterministic engineering discoveries into a representation
    optimized for human understanding.

    The compiler is deterministic and stateless. Same inputs always produce
    the same PresentationIR.

    IMPORTANT: The Presentation Compiler NEVER discovers relationships.
    It only formats discoveries for humans.

    Input: DiscoveryIR
    Output: PresentationIR
    """

    def __init__(self) -> None:
        """Initialize the compiler with presentation-only passes."""
        self.passes = [
            NormalizationPass(),              # Pass 0
            DiscoveryExtractionPass(),         # Pass 1
            NarrativeConstructionPass(),       # Pass 2
            VisualCompositionPass(),           # Pass 3
            IRAssemblyPass(),                  # Pass 4
        ]

    def compile(
        self,
        discovery_ir: DiscoveryIR,
    ) -> PresentationIR:
        """
        Compile a DiscoveryIR into a PresentationIR.

        Args:
            discovery_ir: The DiscoveryIR to format for presentation.

        Returns:
            PresentationIR containing the structured presentation output.

        Raises:
            ValueError: If discovery_ir is invalid.
            RuntimeError: If pipeline completes without producing IR.
        """
        if discovery_ir is None:
            raise ValueError("discovery_ir is required")

        # Initialize pass context with the discovery IR
        context = PresentationPassContext(
            discovery_ir=discovery_ir,
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
        discovery_ir: DiscoveryIR,
    ) -> PresentationPassContext:
        """
        Compile and return the full pass context.

        This is useful for debugging and testing. It returns the full
        context after all passes have executed, which includes all
        intermediate state.

        Args:
            discovery_ir: The DiscoveryIR to format for presentation.

        Returns:
            PresentationPassContext with all intermediate state.
        """
        if discovery_ir is None:
            raise ValueError("discovery_ir is required")

        context = PresentationPassContext(
            discovery_ir=discovery_ir,
        )

        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        return context
