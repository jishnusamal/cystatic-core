"""Pipeline execution context.

Tracks runtime state through the pipeline execution.
No compiler logic - pure orchestration state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from core.runtime import RunContext

if TYPE_CHECKING:
    from engine.repository.model import RepositoryModel
    from engine.change.model import ChangeModel, RepositoryDelta
    from engine.behavior.model import BehaviorModel
    from engine.operational.model import OperationalChangeModel, EngineeringDiscoveryModel
    from engine.operational.discovery.model import DiscoveryIR
    from engine.review_context.model import ReviewContext
    from engine.llm_context.model import LLMContext


@dataclass
class PipelineContext:
    """
    Runtime state for a single pipeline execution.

    Tracks all intermediate artifacts and metadata through the pipeline.
    This is NOT a compiler context - it's pure orchestration state.
    """

    # Input
    repository: str
    run_context: RunContext | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    diff_data: dict[str, Any] | None = None

    # Repository snapshots (immutable once set)
    base_repository_snapshot: Any | None = None
    head_repository_snapshot: Any | None = None

    # Compiled repository models (immutable once set)
    base_repository_model: RepositoryModel | None = None
    head_repository_model: RepositoryModel | None = None
    repository_view: Any | None = None

    # Repository delta (canonical input for downstream phases)
    repository_delta: RepositoryDelta | None = None

    # Intermediate artifacts
    change_model: ChangeModel | None = None
    behavior_model: BehaviorModel | None = None
    ocm: OperationalChangeModel | None = None
    edm: EngineeringDiscoveryModel | None = None

    # Discovery IR (output of Discovery Compiler)
    discovery_ir: DiscoveryIR | None = None

    # ReviewContext (output of ReviewContext Compiler)
    review_context: ReviewContext | None = None

    # LLMContext (output of LLMContext Compiler)
    llm_context: LLMContext | None = None

    # Metadata
    language: str | None = None
    adapter: str | None = None
    request_id: str | None = None
    installation_id: str | None = None

    # Timing
    compile_started_at: float | None = None
    repository_compile_time: float | None = None
    change_compile_time: float | None = None
    behavior_compile_time: float | None = None
    operational_compile_time: float | None = None
    discovery_compile_time: float | None = None
    presentation_compile_time: float | None = None
    llm_compile_time: float | None = None
    render_time: float | None = None
    total_time: float | None = None

    # Errors
    error: Exception | None = None

    def mark_compilation_start(self) -> None:
        """Record the start time of compilation."""
        import time
        self.compile_started_at = time.time()

    def mark_repository_compiled(self) -> None:
        """Record repository compilation completion."""
        import time
        if self.compile_started_at:
            self.repository_compile_time = time.time() - self.compile_started_at

    def mark_change_compiled(self) -> None:
        """Record change compilation completion."""
        import time
        if self.compile_started_at:
            self.change_compile_time = time.time() - self.compile_started_at

    def mark_behavior_compiled(self) -> None:
        """Record behavior compilation completion."""
        import time
        if self.compile_started_at:
            self.behavior_compile_time = time.time() - self.compile_started_at

    def mark_operational_compiled(self) -> None:
        """Record operational compilation completion."""
        import time
        if self.compile_started_at:
            self.operational_compile_time = time.time() - self.compile_started_at

    def mark_discovery_compiled(self) -> None:
        """Record discovery compilation completion."""
        import time
        if self.compile_started_at:
            self.discovery_compile_time = time.time() - self.compile_started_at

    def mark_presentation_compiled(self) -> None:
        """Record presentation compilation completion."""
        import time
        if self.compile_started_at:
            self.presentation_compile_time = time.time() - self.compile_started_at

    def mark_render_complete(self) -> None:
        """Record rendering completion."""
        import time
        if self.compile_started_at:
            self.render_time = time.time() - self.compile_started_at

    def mark_complete(self) -> None:
        """Record total execution time."""
        import time
        if self.compile_started_at:
            self.total_time = time.time() - self.compile_started_at

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for logging/serialization."""
        return {
            "run_id": self.run_context.run_id if self.run_context else None,
            "log_dir": str(self.run_context.log_dir) if self.run_context else None,
            "repository": self.repository,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "language": self.language,
            "adapter": self.adapter,
            "request_id": self.request_id,
            "installation_id": self.installation_id,
            "has_base_model": self.base_repository_model is not None,
            "has_head_model": self.head_repository_model is not None,
            "repository_compile_time": self.repository_compile_time,
            "change_compile_time": self.change_compile_time,
            "behavior_compile_time": self.behavior_compile_time,
            "operational_compile_time": self.operational_compile_time,
            "has_discovery_model": self.edm is not None,
            "has_discovery_ir": self.discovery_ir is not None,
            "has_review_context": self.review_context is not None,
            "has_llm_context": self.llm_context is not None,
            "render_time": self.render_time,
            "total_time": self.total_time,
            "has_error": self.error is not None,
        }
