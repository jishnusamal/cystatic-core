"""Backward-compatibility shim. Import from engine.pipeline instead."""

from engine.pipeline.context import PipelineContext
from engine.pipeline.pipeline import Pipeline

__all__ = ["Pipeline", "PipelineContext"]
