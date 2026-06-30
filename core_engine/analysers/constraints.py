"""
Constraint Analyzer

Extracts business and operational invariants.
Examples: Payment must be authorized, Retry must be idempotent, Order must exist, One invoice per payment
"""
from __future__ import annotations

from typing import Any
from core_engine.analysers.base import EvidenceAnalyzer, AnalyzerOutput
from core_engine.analysers.analysis_context import AnalysisContext


class ConstraintAnalyzer(EvidenceAnalyzer):
    """Extract business and operational invariants.
    
    This analyzer:
    - Identifies constraint patterns in the code
    - Extracts business rules and operational invariants
    - Never predicts failures
    - Only extracts deterministic constraint facts
    """
    
    # Constraint patterns
    CONSTRAINT_PATTERNS = {
        "idempotency": {
            "keywords": ["idempotent", "idempotency", "duplicate", "once", "unique"],
            "patterns": ["check_duplicate", "ensure_once", "prevent_duplicate"],
        },
        "authorization_required": {
            "keywords": ["authorize", "authenticate", "permission", "login_required"],
            "patterns": ["@login_required", "@auth_required", "require_auth", "check_permission"],
        },
        "transaction_boundary": {
            "keywords": ["transaction", "atomic", "commit", "rollback"],
            "patterns": ["@transaction", "with_transaction", "begin_transaction"],
        },
        "validation_required": {
            "keywords": ["validate", "validation", "required", "must_have"],
            "patterns": ["validate_", "check_required", "ensure_valid"],
        },
        "state_consistency": {
            "keywords": ["consistent", "sync", "synchronize", "state"],
            "patterns": ["ensure_consistent", "sync_state", "maintain_consistency"],
        },
        "order_dependency": {
            "keywords": ["order", "sequence", "before", "after", "prerequisite"],
            "patterns": ["must_precede", "requires", "depends_on"],
        },
        "uniqueness": {
            "keywords": ["unique", "distinct", "one_per", "single"],
            "patterns": ["unique_", "ensure_unique", "one_per_"],
        },
        "retry_safety": {
            "keywords": ["retry", "safe", "recoverable", "resilient"],
            "patterns": ["safe_retry", "retry_safe", "can_retry"],
        },
    }
    
    def analyze(self, context: AnalysisContext) -> AnalyzerOutput:
        """Extract constraints from the analysis context.
        
        Args:
            context: AnalysisContext containing enriched_files with hunks.
            
        Returns:
            AnalyzerOutput with constraints populated.
        """
        output = AnalyzerOutput()
        
        # Extract from enriched_files
        for file_data in context.enriched_files:
            file_path = file_data.get("file_path", "")
            changed_functions = file_data.get("changed_functions", [])
            hunks = file_data.get("hunks", [])
            
            # Get added lines
            added_lines = self._extract_added_lines(hunks)
            removed_lines = self._extract_removed_lines(hunks)
            
            # Check for constraint patterns
            for constraint_type, patterns in self.CONSTRAINT_PATTERNS.items():
                # Check added lines
                for line in added_lines:
                    line_lower = line.lower()
                    
                    # Check keywords
                    for keyword in patterns["keywords"]:
                        if keyword in line_lower:
                            output.constraints.append({
                                "constraint": constraint_type,
                                "constraint_type": "operational_invariant",
                                "value": "enforced",
                                "severity": "high",
                                "source": file_path,
                                "evidence": f"Added line contains constraint keyword '{keyword}': {line[:100]}",
                                "file_path": file_path,
                            })
                            break
                    
                    # Check specific patterns
                    for pattern in patterns["patterns"]:
                        if pattern in line_lower:
                            output.constraints.append({
                                "constraint": constraint_type,
                                "constraint_type": "operational_invariant",
                                "value": "enforced",
                                "severity": "high",
                                "source": file_path,
                                "evidence": f"Added line contains constraint pattern '{pattern}': {line[:100]}",
                                "file_path": file_path,
                            })
                            break
                
                # Check removed lines (constraint removal is important)
                for line in removed_lines:
                    line_lower = line.lower()
                    
                    for keyword in patterns["keywords"]:
                        if keyword in line_lower:
                            output.constraints.append({
                                "constraint": constraint_type,
                                "constraint_type": "operational_invariant",
                                "value": "removed",
                                "severity": "critical",
                                "source": file_path,
                                "evidence": f"Removed line contained constraint keyword '{keyword}': {line[:100]}",
                                "file_path": file_path,
                            })
                            break
            
            # Check changed functions for constraint-related names
            for func in changed_functions:
                func_name = self._get_func_name(func).lower()
                
                for constraint_type, patterns in self.CONSTRAINT_PATTERNS.items():
                    for pattern in patterns["patterns"]:
                        if pattern in func_name:
                            output.constraints.append({
                                "constraint": constraint_type,
                                "constraint_type": "function_naming",
                                "value": "enforced",
                                "severity": "medium",
                                "source": func_name,
                                "evidence": f"Function name '{func_name}' suggests constraint enforcement",
                                "file_path": file_path,
                            })
        
        # Extract from risk patterns
        for risk_pattern in context.risk_patterns:
            risk_dict = self._to_dict(risk_pattern)
            risk_type = risk_dict.get("type", "")
            
            # Map risk patterns to constraints
            constraint_mapping = {
                "VALIDATION_REMOVED": ("validation_required", "removed", "critical"),
                "AUTH_BYPASS": ("authorization_required", "removed", "critical"),
                "RETRY_HANDLING": ("retry_safety", "modified", "high"),
                "SCHEMA_MIGRATION": ("state_consistency", "modified", "high"),
            }
            
            if risk_type in constraint_mapping:
                constraint_type, value, severity = constraint_mapping[risk_type]
                output.constraints.append({
                    "constraint": constraint_type,
                    "constraint_type": "risk_inferred",
                    "value": value,
                    "severity": severity,
                    "source": risk_dict.get("file_path", ""),
                    "evidence": f"Risk pattern '{risk_type}' suggests constraint change",
                    "file_path": risk_dict.get("file_path", ""),
                })
        
        # Deduplicate constraints
        output.constraints = self._dedupe(output.constraints)
        
        return output
    
    def _extract_added_lines(self, hunks: list[Any]) -> list[str]:
        """Extract added lines from hunks."""
        added_lines = []
        
        for hunk in hunks:
            hunk_dict = self._to_dict(hunk)
            lines = hunk_dict.get("lines", [])
            
            for line in lines:
                line_dict = self._to_dict(line)
                if line_dict.get("line_type") == "added":
                    content = str(line_dict.get("content", ""))
                    if content.strip():
                        added_lines.append(content)
        
        return added_lines
    
    def _extract_removed_lines(self, hunks: list[Any]) -> list[str]:
        """Extract removed lines from hunks."""
        removed_lines = []
        
        for hunk in hunks:
            hunk_dict = self._to_dict(hunk)
            lines = hunk_dict.get("lines", [])
            
            for line in lines:
                line_dict = self._to_dict(line)
                if line_dict.get("line_type") == "removed":
                    content = str(line_dict.get("content", ""))
                    if content.strip():
                        removed_lines.append(content)
        
        return removed_lines
    
    def _get_func_name(self, func: Any) -> str:
        """Extract function name from function object."""
        if isinstance(func, dict):
            return func.get("name", "")
        if hasattr(func, "model_dump"):
            return func.model_dump().get("name", "")
        if hasattr(func, "name"):
            return func.name
        return ""
    
    def _to_dict(self, value: Any) -> dict[str, Any]:
        """Convert value to dict."""
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return {}
    
    def _dedupe(self, constraints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate constraints."""
        seen = set()
        unique = []
        for constraint in constraints:
            key = (
                constraint.get("constraint"),
                constraint.get("source"),
                constraint.get("value"),
            )
            if key not in seen:
                seen.add(key)
                unique.append(constraint)
        return unique