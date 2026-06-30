"""
AnalysisContext — shared context for all evidence analyzers.

Built once by the orchestrator, used by every analyzer.
No analyzer reparses code or calls external services.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class AnalysisContext(BaseModel):
    """Shared context for all evidence analyzers.
    
    Built once by the orchestrator and passed to every analyzer.
    Contains all information needed for deterministic analysis.
    
    Attributes:
        diff: The PR diff information.
        changed_files: List of changed file paths.
        asts: Parsed ASTs for changed files.
        repo_metadata: Repository metadata (name, owner, etc.).
        repo_index: Repository-wide symbol index.
        file_snapshots: Full file contents at the PR head SHA.
        language_adapter: The language adapter used for parsing.
        pr_metadata: PR metadata (number, title, author, etc.).
        configuration: Analysis configuration options.
        enriched_files: Pre-processed file data with functions, endpoints, signals.
        risk_patterns: Detected risk patterns from the diff.
    """
    diff: dict[str, Any] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    asts: dict[str, Any] = Field(default_factory=dict)
    repo_metadata: dict[str, Any] = Field(default_factory=dict)
    repo_index: Any = None
    file_snapshots: dict[str, str] = Field(default_factory=dict)
    language_adapter: Any = None
    pr_metadata: dict[str, Any] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)
    enriched_files: list[dict[str, Any]] = Field(default_factory=list)
    risk_patterns: list[Any] = Field(default_factory=list)
    
    model_config = {"arbitrary_types_allowed": True}