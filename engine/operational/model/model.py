"""Operational Change Model - the final enriched model for change analysis.

This is the canonical artifact that renderers and AI consume.
It is a composition of all deterministic models produced by the compilation pipeline.
The last stage enriches the object with dependency, data, event, API, validation,
and metrics models.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.behavior.model import BehaviorModel
from engine.change.model import ChangeModel
from engine.repository.model import RepositoryModel


@dataclass(frozen=True)
class OperationalChangeModel:
    """
    The complete operational change model produced by compilation.

    This is a deterministic, immutable composition of all compiler outputs.
    It answers: "What is the full context of this change?"

    The composition stage fills the first three fields (repository, change, behavior).
    The enrichment stage adds dependency, data, event, api, validation,
    and metrics models.

    Attributes:
        repository: Repository model (what the repo contains).
        change: Change model (what exactly changed).
        behavior: Behavior model (what behavior is affected).

        dependency: Dependency model (structural dependencies).
        data: Data model (persistent state affected).
        event: Event model (async interactions).
        api: API model (externally visible interfaces).
        validation: Validation model (test evidence).
        metrics: Discovery metrics (observable metrics).
    """

    repository: RepositoryModel
    change: ChangeModel
    behavior: BehaviorModel

    # Optional enrichment models
    dependency: object | None = field(default=None, compare=False)
    data: object | None = field(default=None, compare=False)
    event: object | None = field(default=None, compare=False)
    api: object | None = field(default=None, compare=False)
    validation: object | None = field(default=None, compare=False)
    metrics: object | None = field(default=None, compare=False)

    def has_all_required_models(self) -> bool:
        """Check that all required models (repository, change, behavior) are present."""
        return (
            self.repository is not None
            and self.change is not None
            and self.behavior is not None
        )

    def has_dependency_model(self) -> bool:
        """Check if a dependency model is present."""
        return self.dependency is not None

    def has_data_model(self) -> bool:
        """Check if a data model is present."""
        return self.data is not None

    def has_event_model(self) -> bool:
        """Check if an event model is present."""
        return self.event is not None

    def has_api_model(self) -> bool:
        """Check if an API model is present."""
        return self.api is not None

    def has_validation_model(self) -> bool:
        """Check if a validation model is present."""
        return self.validation is not None

    def has_metrics_model(self) -> bool:
        """Check if a metrics model is present."""
        return self.metrics is not None

    @property
    def populated_optional_models(self) -> tuple[str, ...]:
        """Get the names of all populated optional models."""
        models: list[str] = []
        if self.has_dependency_model():
            models.append("dependency")
        if self.has_data_model():
            models.append("data")
        if self.has_event_model():
            models.append("event")
        if self.has_api_model():
            models.append("api")
        if self.has_validation_model():
            models.append("validation")
        if self.has_metrics_model():
            models.append("metrics")
        return tuple(models)

    def __repr__(self) -> str:
        """Human-readable representation showing which models are present."""
        parts = ["OperationalChangeModel"]
        parts.append(f"  repository: {type(self.repository).__name__}")
        parts.append(f"  change:     {type(self.change).__name__}")
        parts.append(f"  behavior:   {type(self.behavior).__name__}")
        optional = self.populated_optional_models
        if optional:
            for name in optional:
                parts.append(f"  {name}:    present")
        else:
            parts.append("  (no optional models)")
        return "\n".join(parts)
