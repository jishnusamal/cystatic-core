"""Pipeline stage definitions.

Stub: enumerate the canonical stages of the analysis pipeline.
"""

from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    """Ordered stages in the Factor analysis pipeline."""

    REPOSITORY_COMPILE = "repository_compile"
    CHANGE_COMPILE = "change_compile"
    BEHAVIOR_COMPILE = "behavior_compile"
    DISCOVERY_RUN = "discovery_run"
    OPERATIONAL_COMPILE = "operational_compile"
    REVIEW_CONTEXT_BUILD = "review_context_build"
    LLM_CONTEXT_BUILD = "llm_context_build"
    RENDER = "render"


__all__ = ["Stage"]
