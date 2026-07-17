"""LLM Context data structures.

Defines the contract between the Presentation Compiler and the LLM layer.
The LLM never sees raw evidence - only compact, curated context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# =========================================================================
# LLM Context Models
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