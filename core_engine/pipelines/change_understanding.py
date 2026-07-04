"""
ChangeUnderstandingPipeline — analyzes the PR change itself.

This pipeline is responsible for:
  - Extracting changed files and symbols
  - Enriching files with functions, endpoints, signals
  - Detecting risk patterns
  - Extracting behavior deltas and diffs
  - Detecting side effects
  - Extracting constraints

Output: ChangeUnderstanding
"""
from __future__ import annotations

from typing import Any

from core_engine.behavior_diff_builder import build_behavior_diffs
from core_engine.change_influence import extract_changed_symbols
from core_engine.constraint_extractor import extract_constraints
from core_engine.entrypoint_resolver import EntryPointResolver
from core_engine.models.change_understanding import ChangeUnderstanding
from core_engine.models.constraint import Constraint as ModelConstraint
from core_engine.models.side_effect import SideEffect
from core_engine.reachability_classifier import ReachabilityClassifier
from core_engine.risk_pattern_detector import RiskPatternDetector
from core_engine.side_effect_detector import SideEffectDetector
from core_engine.behavior_extractor import extract_behavior_deltas


class ChangeUnderstandingPipeline:
    """Analyzes the PR change and produces a complete understanding."""
    
    @staticmethod
    def run(
        enriched_files: list[dict[str, Any]],
        diff_ir: Any = None,
        repo_index: Any = None,
    ) -> ChangeUnderstanding:
        """Run the change understanding pipeline.
        
        Args:
            enriched_files: List of enriched file data from the language adapter.
            diff_ir: Optional diff IR from the source adapter.
            repo_index: Optional repository symbol index.
            
        Returns:
            ChangeUnderstanding containing all analysis results.
        """
        print("Detecting risk patterns...")
        risk_detector = RiskPatternDetector()
        risk_patterns = risk_detector.detect(enriched_files)
        
        print("Resolving entry points...")
        resolver = EntryPointResolver()
        entry_points_affected = resolver.resolve(enriched_files, risk_patterns)
        
        print("Extracting behavior deltas...")
        extract_behavior_deltas(enriched_files, risk_patterns)
        behavior_diffs = build_behavior_diffs(enriched_files)
        
        print("Classifying reachability...")
        reachability_classifier = ReachabilityClassifier()
        reachability_classifier.classify_batch(enriched_files)
        
        print("Detecting side effects...")
        side_effect_detector = SideEffectDetector()
        side_effect_dict = side_effect_detector.detect(enriched_files)
        side_effect_results = [
            SideEffect(
                description=f"Side effect detected: {', '.join(sr.details) if sr.details else 'various effects'}",
                symbol="changed_code",
                effect_type=", ".join([
                    "database_write" if sr.database_write else "",
                    "external_call" if sr.external_call else "",
                    "cache_write" if sr.cache_write else "",
                    "queue_publish" if sr.queue_publish else "",
                ]).strip(", "),
                confidence=sr.confidence,
                metadata={"details": sr.details}
            )
            for sr in side_effect_dict.values()
        ] if side_effect_dict else []
        
        print("Extracting constraints...")
        constraints = extract_constraints(enriched_files)
        
        print("Extracting changed symbols...")
        changed_symbols_list = extract_changed_symbols(
            behavior_diffs=behavior_diffs,
            enriched_files=enriched_files,
        )
        
        business_objects = []
        if constraints and constraints.constraints:
            for constraint in constraints.constraints:
                if hasattr(constraint, 'business_objects'):
                    business_objects.extend(constraint.business_objects)
        
        model_constraints = []
        if constraints and constraints.constraints:
            for c in constraints.constraints:
                model_constraints.append(ModelConstraint(
                    constraint=c.constraint,
                    constraint_type=c.type.value,
                    value=c.value.value,
                    severity=c.severity.value,
                    source=c.source,
                    evidence=c.evidence,
                    file_path=c.file_path,
                ))
        
        understanding = ChangeUnderstanding(
            changed_symbols=[],
            risk_anchors=[],
            behavior_diffs=behavior_diffs,
            side_effects=side_effect_results or [],
            constraints=model_constraints,
            business_objects=business_objects,
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected,
        )
        
        print(f"Change understanding complete: {len(risk_patterns)} risk patterns, "
              f"{len(changed_symbols_list)} changed symbols")
        
        return understanding
