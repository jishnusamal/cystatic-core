"""File classification pass - classifies changed files into functional roles.

Pass 0 of the change compiler: runs before ChangedSymbolsPass so that files
which analysis has decided to ignore (e.g. frontend TS/TSX, generated files)
never reach semantic change analysis.
"""

from typing import Any

from engine.change.passes.file_classification import (
    AnalysisPolicy,
    DEFAULT_ANALYSIS_POLICY,
    FileClassification,
    FileClassifier,
    detect_language,
)

from ..base import ChangeCompilerPass, ChangePassContext


class FileClassificationPass(ChangeCompilerPass):
    """
    Pass 0: File Classification

    Classifies every changed file into a functional role and partitions the
    change set into analysis-eligible vs excluded files.

    Input: Git diff data (changed file paths)
    Output: File classifications + exclusion sets used by downstream passes
    """

    def __init__(
        self,
        classifier: FileClassifier | None = None,
        policy: AnalysisPolicy | None = None,
    ) -> None:
        self.classifier = classifier or FileClassifier()
        self.policy = policy or DEFAULT_ANALYSIS_POLICY

    @property
    def name(self) -> str:
        return "file_classification"

    def run(self, context: ChangePassContext) -> ChangePassContext:
        """
        Execute file classification pass.

        Args:
            context: Pass context with diff data containing changed file paths

        Returns:
            Updated context with classifications and eligibility sets
        """
        changed_files = self._extract_changed_files(context.diff_data)

        # Fallback: derive changed files from symbol indices when the diff
        # does not carry explicit file paths.
        if not changed_files:
            old_model = context.metadata.get("old_repository_model")
            new_model = context.metadata.get("new_repository_model")
            for model in (old_model, new_model):
                if model is not None and hasattr(model, "symbols"):
                    changed_files.update(s.file for s in model.symbols)

        classifications: dict[str, FileClassification] = {}
        eligible: set[str] = set()
        excluded: set[str] = set()

        for file_path in sorted(changed_files):
            classification = self.classifier.classify(file_path)
            classifications[file_path] = classification
            language = detect_language(file_path)
            if self.policy.is_analyzable(classification, language):
                eligible.add(file_path)
            else:
                excluded.add(file_path)

        context.file_classifications = classifications
        context.analysis_eligible_files = eligible
        context.excluded_files = excluded
        context.metadata["file_classifications"] = classifications
        context.metadata["analysis_eligible_files"] = eligible
        context.metadata["excluded_files"] = excluded
        context.metadata["classification_summary"] = {
            "eligible_files": len(eligible),
            "excluded_files": len(excluded),
        }

        return context

    def _extract_changed_files(self, diff_data: Any) -> set[str]:
        """Extract changed file paths from diff data.

        Supports plain dicts ({"files": [{"file_path": ...}, ...]}) and
        DiffSnapshot-like objects (.files with file_path/path attributes).
        """
        changed_files: set[str] = set()
        if not diff_data:
            return changed_files

        files: Any = None
        if isinstance(diff_data, dict):
            files = diff_data.get("files")
        elif hasattr(diff_data, "files"):
            files = diff_data.files

        if not files:
            return changed_files

        for f in files:
            if isinstance(f, dict):
                fp = f.get("file_path") or f.get("path")
            else:
                fp = getattr(f, "file_path", None) or getattr(f, "path", None)
            if fp:
                changed_files.add(fp)

        return changed_files
