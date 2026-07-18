"""LLM Narrative Models — what the LLM actually generates.

These models contain ONLY text fields that the LLM is responsible for.
No metrics, no counts, no deterministic data.

The LLM generates:
- executive_summary: 2-3 sentence overview
- review_priority: Priority level with justification
- biggest_surprise: Most surprising finding
- execution_summary: Execution impact in plain language
- operational_summary: Operational changes in plain language
- validation_summary: Validation coverage summary
- attention: What to focus on during review
- surprising_discoveries[].explanation: Why each discovery is surprising
- evidence wording: How to phrase evidence items

The compiler provides everything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NarrativeSurprisingDiscovery:
    """LLM-generated narrative for a surprising discovery.
    
    The compiler provides title, metric, and support.
    The LLM only generates the explanation.
    """
    explanation: str = ""


@dataclass(frozen=True)
class GithubCommentNarrative:
    """LLM-generated narrative for a GitHub comment.
    
    This is the ONLY output the LLM produces.
    No metrics, no counts, no deterministic data.
    The Jinja2 renderer merges this with GithubCommentContext.
    """
    executive_summary: str = ""
    review_priority: str = ""
    biggest_surprise: str = ""
    execution_summary: str = ""
    operational_summary: str = ""
    validation_summary: str = ""
    attention: str = ""
    surprising_discoveries: tuple[NarrativeSurprisingDiscovery, ...] = field(default_factory=tuple)
    evidence: tuple[str, ...] = field(default_factory=tuple)
    
    def __post_init__(self):
        """Normalize mutable defaults to immutable types."""
        if isinstance(self.surprising_discoveries, list):
            discoveries = []
            for item in self.surprising_discoveries:
                if isinstance(item, dict):
                    discoveries.append(NarrativeSurprisingDiscovery(
                        explanation=item.get('explanation', ''),
                    ))
                elif isinstance(item, NarrativeSurprisingDiscovery):
                    discoveries.append(item)
            object.__setattr__(self, 'surprising_discoveries', tuple(discoveries))
        if isinstance(self.evidence, list):
            object.__setattr__(self, 'evidence', tuple(self.evidence))