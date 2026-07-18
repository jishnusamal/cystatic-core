"""GithubCommentContext — deterministic presentation context for GitHub comments.

This model contains ALL compiler-derived facts that the Jinja2 renderer needs.
The LLM never generates these values. They come directly from the PresentationIR.

The LLM only generates narrative text (summaries, explanations, priorities).
The context owns all metrics, counts, paths, and evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextSurprisingDiscovery:
    """A surprising discovery with all deterministic data pre-populated.
    
    The LLM only generates the 'explanation' field.
    Everything else comes from the compiler.
    """
    title: str
    explanation: str = ""
    metric: str = ""
    support: str = ""


@dataclass(frozen=True)
class ContextExecutionSection:
    """Execution impact section — ALL fields are compiler-derived.
    
    The LLM never generates execution_paths, reachable_units, or depth.
    These are populated from the PresentationIR before the LLM is called.
    """
    execution_paths: int = 0
    reachable_units: int = 0
    depth: int = 0
    narrative: str = ""
    highlights: tuple[ContextSurprisingDiscovery, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContextOperationalSection:
    """Operational impact section — ALL fields are compiler-derived.
    
    The LLM never generates api_count, data_count, event_count, or dependency_count.
    These are populated from the PresentationIR before the LLM is called.
    """
    api_count: int = 0
    data_count: int = 0
    event_count: int = 0
    dependency_count: int = 0
    behavior_count: int = 0
    symbol_count: int = 0
    narrative: str = ""


@dataclass(frozen=True)
class ContextValidationSection:
    """Validation coverage section — compiler-derived.
    
    The LLM only generates the summary text.
    """
    summary: str = ""
    gap_count: int = 0


@dataclass(frozen=True)
class GithubCommentContext:
    """Complete deterministic context for GitHub comment rendering.
    
    This is the ONLY source of truth for all metrics in the rendered comment.
    The LLM never generates, copies, or reconstructs any of these values.
    
    The renderer (Jinja2) reads directly from this context for all metrics.
    The LLM only provides narrative text that wraps around these facts.
    
    Pipeline:
        PresentationIR → PresentationContextBuilder → GithubCommentContext
                                                              ↓
        LLM Narrative Generator (only generates text fields)   ↓
                                                              ↓
        Merge → GithubComment → Jinja2 Renderer → Markdown
    """
    # Summary
    executive_summary: str = ""
    review_priority: str = ""
    biggest_surprise: str = ""
    
    # Execution
    execution: ContextExecutionSection = field(default_factory=ContextExecutionSection)
    execution_summary: str = ""
    
    # Operational
    operational: ContextOperationalSection = field(default_factory=ContextOperationalSection)
    operational_summary: str = ""
    
    # Validation
    validation: ContextValidationSection = field(default_factory=ContextValidationSection)
    validation_summary: str = ""
    
    # Discoveries
    attention: str = ""
    surprising_discoveries: tuple[ContextSurprisingDiscovery, ...] = field(default_factory=tuple)
    
    # Evidence
    evidence: tuple[str, ...] = field(default_factory=tuple)
    
    # Pipeline diagnostics (not rendered, used for logging)
    pipeline_diagnostics: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Normalize mutable defaults to immutable types."""
        if isinstance(self.surprising_discoveries, list):
            object.__setattr__(self, 'surprising_discoveries', tuple(self.surprising_discoveries))
        if isinstance(self.evidence, list):
            object.__setattr__(self, 'evidence', tuple(self.evidence))
        if isinstance(self.execution, dict):
            exec_data = self.execution
            highlights = exec_data.get('highlights', [])
            if isinstance(highlights, list):
                highlight_objects = tuple(
                    ContextSurprisingDiscovery(
                        title=h.get('title', ''),
                        explanation=h.get('explanation', ''),
                        metric=h.get('metric', ''),
                        support=h.get('support', ''),
                    ) if isinstance(h, dict) else h
                    for h in highlights
                )
            else:
                highlight_objects = highlights
            object.__setattr__(self, 'execution', ContextExecutionSection(
                execution_paths=int(exec_data.get('execution_paths', 0)),
                reachable_units=int(exec_data.get('reachable_units', 0)),
                depth=int(exec_data.get('depth', 0)),
                narrative=str(exec_data.get('narrative', '')),
                highlights=highlight_objects,
            ))
        if isinstance(self.operational, dict):
            op_data = self.operational
            object.__setattr__(self, 'operational', ContextOperationalSection(
                api_count=int(op_data.get('api_count', 0)),
                data_count=int(op_data.get('data_count', 0)),
                event_count=int(op_data.get('event_count', 0)),
                dependency_count=int(op_data.get('dependency_count', 0)),
                behavior_count=int(op_data.get('behavior_count', 0)),
                symbol_count=int(op_data.get('symbol_count', 0)),
                narrative=str(op_data.get('narrative', '')),
            ))
        if isinstance(self.validation, dict):
            val_data = self.validation
            object.__setattr__(self, 'validation', ContextValidationSection(
                summary=str(val_data.get('summary', '')),
                gap_count=int(val_data.get('gap_count', 0)),
            ))