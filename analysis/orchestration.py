"""Pipeline orchestration entry point.

Thin entry point that delegates to engine/pipeline/pipeline.py.
"""

from __future__ import annotations

from engine.pipeline.pipeline import Pipeline
from engine.pipeline.context import PipelineContext

__all__ = ["Pipeline", "PipelineContext"]
