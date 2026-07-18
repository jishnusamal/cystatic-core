"""LLM Context and Output data structures.

Defines the contract between the Presentation Compiler and the LLM layer.
The LLM never sees raw evidence - only compact, curated context.
The LLM returns structured JSON, never markdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# =========================================================================
# LLM Context Models (Input to LLM)
# =========================================================================


@dataclass(frozen=True)
class LLMDiscovery:
    """Compact representation of a discovery for LLM consumption.
    
    Contains only the information the LLM needs to write a narrative.
    No raw evidence - just top representative examples.
    """
    id: str
    kind: str
    title: str
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    surprise: dict[str, Any] = field(default_factory=dict)
    top_evidence: tuple[str, ...] = field(default_factory=tuple)  # Max 5 items
    narrative_position: str = ""


@dataclass(frozen=True)
class LLMNarrative:
    """Narrative section for LLM consumption."""
    section: str
    order: int
    description: str
    discovery_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LLMVisual:
    """Visual semantic for LLM consumption."""
    discovery_id: str
    semantic: str
    value: str | int | float
    label: str


@dataclass(frozen=True)
class LLMContext:
    """Compact context for LLM comment generation.
    
    This is the ONLY data the LLM receives.
    No raw evidence, no AST, no graphs, no repository structure.
    
    The LLM can only:
    - summarize
    - prioritize
    - explain
    - organize
    - rewrite
    
    It must never invent new discoveries, risks, or metrics.
    """
    metadata: dict[str, Any]
    summary: dict[str, Any]
    discoveries: tuple[LLMDiscovery, ...]
    narrative: tuple[LLMNarrative, ...]
    visuals: tuple[LLMVisual, ...]
    constraints: tuple[str, ...] = (
        "Never invent new behaviors.",
        "Never speculate about bugs.",
        "Never recommend code changes.",
        "Only summarize deterministic discoveries from the provided context.",
        "Never add additional risks, blast radius, dependencies, or failures not in the context.",
    )
    
    def __post_init__(self):
        """Normalize mutable defaults to immutable types."""
        if isinstance(self.discoveries, list):
            object.__setattr__(self, 'discoveries', tuple(self.discoveries))
        if isinstance(self.narrative, list):
            object.__setattr__(self, 'narrative', tuple(self.narrative))
        if isinstance(self.visuals, list):
            object.__setattr__(self, 'visuals', tuple(self.visuals))
        if isinstance(self.constraints, list):
            object.__setattr__(self, 'constraints', tuple(self.constraints))


# =========================================================================
# LLM Output Models (Structured JSON from LLM)
# =========================================================================


@dataclass(frozen=True)
class SurprisingDiscovery:
    """A surprising discovery from the analysis."""
    title: str
    explanation: str
    metric: str = ""
    support: str = ""


@dataclass(frozen=True)
class ExecutionSection:
    """Execution impact section."""
    execution_paths: int = 0
    reachable_units: int = 0
    depth: int = 0
    narrative: str = ""
    highlights: tuple[SurprisingDiscovery, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class OperationalSection:
    """Operational impact section."""
    api_count: int = 0
    data_count: int = 0
    event_count: int = 0
    dependency_count: int = 0
    narrative: str = ""


@dataclass(frozen=True)
class ValidationSection:
    """Validation coverage section."""
    summary: str = ""


@dataclass(frozen=True)
class GithubComment:
    """Structured GitHub comment from LLM.
    
    This is the ONLY output the LLM produces.
    No markdown, no formatting - just structured data.
    The Jinja2 renderer converts this to markdown.
    """
    executive_summary: str
    review_priority: str
    biggest_surprise: str
    execution_summary: str
    operational_summary: str
    validation_summary: str
    attention: str
    surprising_discoveries: tuple[SurprisingDiscovery, ...] = field(default_factory=tuple)
    execution: ExecutionSection = field(default_factory=ExecutionSection)
    operational: OperationalSection = field(default_factory=OperationalSection)
    validation: ValidationSection = field(default_factory=ValidationSection)
    evidence: tuple[str, ...] = field(default_factory=tuple)
    
    def __post_init__(self):
        """Normalize mutable defaults to immutable types."""
        # Convert surprising_discoveries list to tuple of SurprisingDiscovery objects
        if isinstance(self.surprising_discoveries, list):
            discoveries = []
            for item in self.surprising_discoveries:
                if isinstance(item, dict):
                    discoveries.append(SurprisingDiscovery(
                        title=item.get('title', ''),
                        explanation=item.get('explanation', ''),
                        metric=item.get('metric', ''),
                        support=item.get('support', ''),
                    ))
                elif isinstance(item, SurprisingDiscovery):
                    discoveries.append(item)
            object.__setattr__(self, 'surprising_discoveries', tuple(discoveries))
        
        if isinstance(self.evidence, list):
            object.__setattr__(self, 'evidence', tuple(self.evidence))
        
        # Convert execution dict to ExecutionSection
        if isinstance(self.execution, dict):
            exec_data = self.execution
            highlights = exec_data.get('highlights', [])
            if isinstance(highlights, list):
                highlight_objects = []
                for h in highlights:
                    if isinstance(h, dict):
                        highlight_objects.append(SurprisingDiscovery(
                            title=h.get('title', ''),
                            explanation=h.get('explanation', ''),
                            metric=h.get('metric', ''),
                            support=h.get('support', ''),
                        ))
                    elif isinstance(h, SurprisingDiscovery):
                        highlight_objects.append(h)
                highlights = tuple(highlight_objects)
            object.__setattr__(self, 'execution', ExecutionSection(
                execution_paths=int(exec_data.get('execution_paths', 0)),
                reachable_units=int(exec_data.get('reachable_units', 0)),
                depth=int(exec_data.get('depth', 0)),
                narrative=str(exec_data.get('narrative', '')),
                highlights=highlights,
            ))
        
        # Convert operational dict to OperationalSection
        if isinstance(self.operational, dict):
            op_data = self.operational
            object.__setattr__(self, 'operational', OperationalSection(
                api_count=int(op_data.get('api_count', 0)),
                data_count=int(op_data.get('data_count', 0)),
                event_count=int(op_data.get('event_count', 0)),
                dependency_count=int(op_data.get('dependency_count', 0)),
                narrative=str(op_data.get('narrative', '')),
            ))
        
        # Convert validation dict to ValidationSection
        if isinstance(self.validation, dict):
            val_data = self.validation
            object.__setattr__(self, 'validation', ValidationSection(
                summary=str(val_data.get('summary', '')),
            ))
