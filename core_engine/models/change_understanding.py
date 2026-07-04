"""
ChangeUnderstanding — represents the complete understanding of a PR change.

This is the output of the ChangeUnderstandingPipeline and the input to the
EvidencePipeline.

Contains:
  - Changed symbols
  - Risk patterns
  - Behavior diffs
  - Side effects
  - Constraints
  - Business objects
  - Enriched files
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .changed_symbol import ChangedSymbol
from .risk_anchor import RiskAnchor
from .side_effect import SideEffect
from .constraint import Constraint
from .business_object import BusinessObject


class ChangeUnderstanding(BaseModel):
    """Complete understanding of a PR change.
    
    This is the output of ChangeUnderstandingPipeline and the input to
    EvidencePipeline. It contains all deterministic analysis of the change
    itself, before semantic evidence generation.
    
    Attributes:
        changed_symbols: All symbols modified by the change.
        risk_anchors: Changes known to increase downstream uncertainty.
        behavior_diffs: Behavior-level deltas from the change.
        side_effects: Side effects introduced or affected by the change.
        constraints: Constraints that apply to the change.
        business_objects: Business objects referenced by the change.
        enriched_files: Enriched file data from the analysis.
        risk_patterns: Detected risk patterns.
        entry_points_affected: Entry points affected by the change.
    """
    changed_symbols: list[ChangedSymbol] = Field(default_factory=list)
    
    risk_anchors: list[RiskAnchor] = Field(default_factory=list)
    
    behavior_diffs: list[Any] = Field(default_factory=list)
    
    side_effects: list[SideEffect] = Field(default_factory=list)
    
    constraints: list[Constraint] = Field(default_factory=list)
    
    business_objects: list[BusinessObject] = Field(default_factory=list)
    
    enriched_files: list[dict[str, Any]] = Field(default_factory=list)
    
    risk_patterns: list[Any] = Field(default_factory=list)
    
    entry_points_affected: list[Any] = Field(default_factory=list)