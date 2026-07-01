"""
InputPreparationPipeline — prepares analysis inputs based on mode.

This pipeline is responsible for:
  - Fetching diff IR from source
  - Extracting changed files
  - Enriching files with language-specific information
  - Building repo index (FULL_FILE mode)
  - Filtering excluded files

Output: PreparedInputs containing enriched_files, diff_ir, repo_index, excluded_files
"""
from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field

from schemas import DiffIR
from language_adapters.python.python_adapter import AnalysisMode
from core_engine.file_exclusion import FileExclusionService

@dataclass
class PreparedInputs:
    """Container for prepared analysis inputs.
    
    Attributes:
        enriched_files: List of enriched file data from the language adapter.
        diff_ir: The diff IR from the source adapter.
        repo_index: Optional repository symbol index (FULL_FILE mode only).
        excluded_files: List of files that were excluded from analysis.
    """
    enriched_files: list[dict[str, Any]] = field(default_factory=list)
    diff_ir: DiffIR | None = None
    repo_index: Any = None
    excluded_files: list[dict[str, Any]] = field(default_factory=list)


class InputPreparationPipeline:
    """Prepares analysis inputs based on the analysis mode.
    
    This pipeline handles the initial data gathering and preparation,
    supporting both DIFF_ONLY (no repo access) and FULL_FILE (with repo access) modes.
    """
    
    @staticmethod
    def run(
        request: Any,
        source: Any,
        language: Any,
        mode: str = "DIFF_ONLY",
    ) -> PreparedInputs:
        """Run the input preparation pipeline.
        
        Args:
            request: The analysis request (AnalyzeRequest or dict).
            source: The source adapter (e.g., GitHub adapter).
            language: The language adapter (e.g., PythonAdapter).
            mode: Analysis mode - either "DIFF_ONLY" or "FULL_FILE".
            
        Returns:
            PreparedInputs containing all necessary inputs for the analysis pipeline.
        """
        print(f"Preparing inputs in {mode} mode...")
        
        # Stage 1: Fetch diff from source
        diff_ir = source.fetch_diff(
            repo=request.repo if hasattr(request, 'repo') else request.get("repo"),
            pr_number=request.pr_number if hasattr(request, 'pr_number') else request.get("pr_number"),
        )
        
        # Stage 2: Apply file exclusions
        file_exclusion = FileExclusionService()
        kept_files = []
        excluded_files = []
        
        for file in diff_ir.files:
            file_path = getattr(file, "file_path", "")
            matched = file_exclusion.get_exclusion_match(file_path)
            if not matched:
                kept_files.append(file)
            else:
                excluded_files.append({
                    "file_path": file_path,
                    "reason": matched,
                })
        
        diff_ir.files = kept_files
        
        # Stage 3: Extract changed files using language adapter
        files = language.extract_changed_files(diff_ir) or []
        
        # Stage 4: Enrich files based on mode
        enriched_files = []
        file_snapshots = {}
        repo_index = None
        
        if mode == "FULL_FILE":
            # FULL_FILE mode: fetch full file snapshots and build repo index
            sha = source.get_head_sha(
                repo=request.repo if hasattr(request, 'repo') else request.get("repo"),
                pr_number=request.pr_number if hasattr(request, 'pr_number') else request.get("pr_number"),
            )
            
            for file in files:
                file_path = file["file_path"]
                
                # Fetch full file snapshot
                try:
                    snapshot = source.fetch_file_at_sha(
                        repo=request.repo if hasattr(request, 'repo') else request.get("repo"),
                        file_path=file_path,
                        sha=sha,
                    )
                    file_snapshots[file_path] = snapshot.content
                except Exception:
                    file_snapshots[file_path] = ""
                
                # Extract language-specific information
                changed_functions = language.extract_changed_functions(
                    file=file,
                    mode=AnalysisMode.FULL_FILE,
                    content=file_snapshots[file_path],
                )
                keyword_signals = language.extract_keyword_signals_from_diff(file=file)
                endpoints = language.extract_endpoints(
                    file_path=file_path,
                    content=file_snapshots[file_path],
                )
                
                # Build enriched file
                changed_function_names = {fn.name for fn in changed_functions}
                impacted_endpoints = [
                    ep for ep in endpoints if ep["function"] in changed_function_names
                ]
                
                enriched_file = {
                    "file_path": file_path,
                    "lines_changed": file.get("lines_changed", 0),
                    "hunks": getattr(file, "hunks", []),
                    "total_functions_changed": len(changed_functions),
                    "total_endpoints": len(impacted_endpoints),
                    "total_keyword_signals": len(keyword_signals),
                    "changed_functions": changed_functions,
                    "endpoints": impacted_endpoints,
                    "keyword_signals": keyword_signals,
                }
                enriched_files.append(enriched_file)
            
            # Build repo index
            try:
                from core_engine.causal_graph import RepositorySymbolIndex
                repo_index = RepositorySymbolIndex.from_files(list(file_snapshots.items()))
            except Exception:
                repo_index = None
                
        elif mode == "DIFF_ONLY":
            # DIFF_ONLY mode: work with diff hunks only, no repo access
            for file in files:
                file_path = file["file_path"]
                
                # Extract language-specific information from diff only
                changed_functions = language.extract_changed_functions(
                    file=file,
                    mode=AnalysisMode.DIFF_ONLY,
                )
                keyword_signals = language.extract_keyword_signals_from_diff(file=file)
                endpoints = language.extract_endpoints_from_diff_only(file=file)
                
                # Build enriched file
                changed_function_names = {fn.name for fn in changed_functions}
                impacted_endpoints = [
                    ep for ep in endpoints if ep["function"] in changed_function_names
                ]
                
                enriched_file = {
                    "file_path": file_path,
                    "lines_changed": file.get("lines_changed", 0),
                    "hunks": getattr(file, "hunks", []),
                    "total_functions_changed": len(changed_functions),
                    "total_endpoints": len(impacted_endpoints),
                    "total_keyword_signals": len(keyword_signals),
                    "changed_functions": changed_functions,
                    "endpoints": impacted_endpoints,
                    "keyword_signals": keyword_signals,
                }
                enriched_files.append(enriched_file)
        
        print(f"Input preparation complete: {len(enriched_files)} enriched files, "
              f"{len(excluded_files)} excluded files")
        
        return PreparedInputs(
            enriched_files=enriched_files,
            diff_ir=diff_ir,
            repo_index=repo_index,
            excluded_files=excluded_files,
        )