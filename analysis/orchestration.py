"""Pipeline orchestration entry point.

Thin entry point that delegates to engine/pipeline/pipeline.py.
"""

from __future__ import annotations

from engine.pipeline.context import PipelineContext
from engine.pipeline.pipeline import Pipeline

__all__ = ["Pipeline", "PipelineContext"]
