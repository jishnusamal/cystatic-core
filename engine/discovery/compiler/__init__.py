"""Discovery Compiler - standalone compiler for deterministic engineering discoveries.

The Discovery Compiler answers:
    Which deterministic engineering observations can be extracted from the Operational Model?

It consumes the OperationalChangeModel and produces a DiscoveryModel.
It is separate from the Operational Compiler and has no presentation logic.

Pass pipeline:
    1. SharedExecutionPass: Identify symbols shared across behaviors
    2. ValidationGapPass: Identify symbols without test coverage
    3. BoundaryCrossingPass: Identify service boundary crossings
    4. HiddenRelationshipPass: Identify non-obvious relationships
    5. DeepExecutionPass: Identify deep execution paths
    6. SharedDependencyPass: Identify shared dependencies
    7. EventPublicationPass: Identify event publications
    8. StateMutationPass: Identify state mutations
    9. PublicInterfaceChangePass: Identify public interface changes

Every pass:
    - Reads from OperationalChangeModel
    - Emits Discovery objects with structured facts
    - Never performs duplicate analysis
    - Is independently testable
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import Any

from engine.operational.model import OperationalChangeModel

from ..model import (
    Discovery,
    DiscoveryFact,
    DiscoveryKind,
    DiscoveryModel,
    DiscoveryReference,
)
from .passes.base import DiscoveryCompilerPass, DiscoveryPassContext
from .passes.boundary_crossing import BoundaryCrossingPass
from .passes.deep_execution import DeepExecutionPass
from .passes.event_publication import EventPublicationPass
from .passes.hidden_relationship import HiddenRelationshipPass
from .passes.public_interface_change import PublicInterfaceChangePass
from .passes.shared_dependency import SharedDependencyPass
from .passes.shared_execution import SharedExecutionPass
from .passes.state_mutation import StateMutationPass
from .passes.validation_gap import ValidationGapPass


class DiscoveryCompiler:
    """Compiles an OperationalChangeModel into a DiscoveryModel.

    This is the deterministic engineering discovery stage.
    It answers questions that normally require manual investigation.

    The compiler is stateless and deterministic. Same inputs always produce
    the same DiscoveryModel.

    Input: OperationalChangeModel
    Output: DiscoveryModel
    """

    COMPILER_VERSION: str = "1.0.0"

    def __init__(self) -> None:
        """Initialize the compiler with all discovery passes."""
        self.passes: list[DiscoveryCompilerPass] = [
            SharedExecutionPass(),  # Pass 1 - Shared execution
            ValidationGapPass(),  # Pass 2 - Validation gaps
            BoundaryCrossingPass(),  # Pass 3 - Boundary crossings
            HiddenRelationshipPass(),  # Pass 4 - Hidden relationships
            DeepExecutionPass(),  # Pass 5 - Deep execution
            SharedDependencyPass(),  # Pass 6 - Shared dependencies
            EventPublicationPass(),  # Pass 7 - Event publications
            StateMutationPass(),  # Pass 8 - State mutations
            PublicInterfaceChangePass(),  # Pass 9 - Public interface changes
        ]

    def compile(
        self,
        operational_model: OperationalChangeModel,
    ) -> DiscoveryModel:
        """Compile an OperationalChangeModel into a DiscoveryModel.

        Args:
            operational_model: The OperationalChangeModel to analyze.

        Returns:
            DiscoveryModel containing all deterministic discoveries.

        Raises:
            ValueError: If operational_model is None.
        """
        if operational_model is None:
            raise ValueError("operational_model is required")

        # Initialize pass context
        context = DiscoveryPassContext(
            operational_model=operational_model,
        )

        # Execute each pass in sequence
        for compiler_pass in self.passes:
            context = compiler_pass.run(context)

        # Build the final DiscoveryModel
        return self._build_discovery_model(context)

    def _build_discovery_model(self, context: DiscoveryPassContext) -> DiscoveryModel:
        """Build the final DiscoveryModel from the pass context.

        Args:
            context: Final pass context with all discoveries.

        Returns:
            Complete DiscoveryModel.
        """
        discoveries = context.discoveries

        # Build metadata
        metadata = {
            "compiler_version": self.COMPILER_VERSION,
            "compiled_at": datetime.now(UTC).isoformat(),
            "discovery_count": len(discoveries),
            "pass_count": len(self.passes),
        }

        return DiscoveryModel(
            discoveries=tuple(discoveries),
            metadata=metadata,
        )

    def get_pass_names(self) -> list[str]:
        """Get the names of all passes in execution order."""
        return [pass_.name for pass_ in self.passes]
