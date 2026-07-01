"""
ChangeUnderstandingPipeline — analyzes the PR change itself.

This pipeline is responsible for:
  - Extracting changed files and symbols
  - Enriching files with functions, endpoints, signals
  - Detecting risk patterns
  - Extracting behavior deltas and diffs
  - Detecting side effects
  - Extracting constraints
  - Building causal graph
  - Building impact evidence
  - Building change influence
  - Building system deltas

Output: ChangeUnderstanding
"""
from __future__ import annotations

from typing import Any

from core_engine.behavior_delta_system import build_system_behavior_deltas
from core_engine.behavior_diff_builder import build_behavior_diffs
from core_engine.causal_graph import build_causal_graph
from core_engine.change_influence import build_change_influence, extract_changed_symbols
from core_engine.constraint_extractor import extract_constraints
from core_engine.entrypoint_resolver import EntryPointResolver
from core_engine.failure_archetype_engine import build_risk_hypotheses
from core_engine.impact_evidence import build_impact_evidence, extract_existing_edges_from_graph
from core_engine.models.change_understanding import ChangeUnderstanding
from core_engine.models.constraint import Constraint as ModelConstraint
from core_engine.models.side_effect import SideEffect
from core_engine.constraint_types import ConstraintSet
from core_engine.reachability_classifier import ReachabilityClassifier
from core_engine.risk_compressor import compress_risk_hypotheses
from core_engine.risk_pattern_detector import RiskPatternDetector
from core_engine.side_effect_detector import SideEffectDetector, SideEffectResult
from core_engine.behavior_extractor import extract_behavior_deltas


class ChangeUnderstandingPipeline:
    """Analyzes the PR change and produces a complete understanding.
    
    This pipeline handles all deterministic analysis of the change itself,
    from file extraction to causal graph construction.
    """
    
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
        # Step 1: Detect risk patterns
        print("Detecting risk patterns...")
        risk_detector = RiskPatternDetector()
        risk_patterns = risk_detector.detect(enriched_files)
        
        # Step 2: Resolve entry points
        print("Resolving entry points...")
        resolver = EntryPointResolver()
        entry_points_affected = resolver.resolve(enriched_files, risk_patterns)
        
        # Step 3: Extract behavior deltas and diffs
        print("Extracting behavior deltas...")
        behavior_deltas = extract_behavior_deltas(enriched_files, risk_patterns)
        behavior_diffs = build_behavior_diffs(enriched_files)
        
        # Step 4: Classify reachability
        print("Classifying reachability...")
        reachability_classifier = ReachabilityClassifier()
        reachability_results = reachability_classifier.classify_batch(enriched_files)
        
        # Step 5: Detect side effects
        print("Detecting side effects...")
        side_effect_detector = SideEffectDetector()
        side_effect_dict = side_effect_detector.detect(enriched_files)
        # Convert SideEffectResult objects to SideEffect models for ChangeUnderstanding
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
        
        # Step 6: Extract constraints
        print("Extracting constraints...")
        constraints = extract_constraints(enriched_files)
        
        # Step 7: Extract changed symbols
        print("Extracting changed symbols...")
        changed_symbols_list = extract_changed_symbols(
            behavior_diffs=behavior_diffs,
            enriched_files=enriched_files,
        )
        
        # Step 8: Build causal graph
        print("Building causal graph...")
        causal_graph = build_causal_graph(
            enriched_files=enriched_files,
            behavior_diffs=behavior_diffs,
            repo_index=repo_index,
        )
        
        # Step 9: Build impact evidence
        print("Building impact evidence...")
        existing_edges = extract_existing_edges_from_graph(causal_graph)
        impact_evidence_list = build_impact_evidence(
            all_changed_symbols=changed_symbols_list,
            existing_edges=existing_edges,
        )
        
        # Step 10: Build change influence
        print("Building change influence...")
        change_influence_entries = build_change_influence(
            all_changed_symbols=changed_symbols_list,
        )
        
        # Step 11: Build system behavior deltas
        print("Building system behavior deltas...")
        system_deltas = build_system_behavior_deltas(
            enriched_files=enriched_files,
            behavior_diffs=behavior_diffs,
            causal_graph=causal_graph,
            failure_template_matches=[],  # Templates are optional
        )
        
        # Step 12: Extract business objects from constraints
        business_objects = []
        if constraints and constraints.constraints:
            for constraint in constraints.constraints:
                if hasattr(constraint, 'business_objects'):
                    business_objects.extend(constraint.business_objects)
        
        # Convert constraint_types.Constraint to models.Constraint for ChangeUnderstanding
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
        
        # Create the ChangeUnderstanding
        understanding = ChangeUnderstanding(
            changed_symbols=[],  # Will be populated by EvidencePipeline if needed
            risk_anchors=[],  # Will be populated by EvidencePipeline if needed
            behavior_diffs=behavior_diffs,
            side_effects=side_effect_results or [],
            constraints=model_constraints,
            business_objects=business_objects,
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected,
            causal_graph=causal_graph,
            system_deltas=system_deltas,
        )
        
        print(f"Change understanding complete: {len(risk_patterns)} risk patterns, "
              f"{len(changed_symbols_list)} changed symbols, {len(system_deltas)} system deltas")
        
        return understanding