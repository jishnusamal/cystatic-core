"""Backward-compatibility shim. Import from core.logging instead."""
from core.logging import PipelineLogger, pipeline_logger
__all__ = ["PipelineLogger", "pipeline_logger"]
