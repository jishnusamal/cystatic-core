from core_engine.constraint_types import (
    Constraint,
    ConstraintSet,
    ConstraintType,
    ConstraintValue,
    ConstraintSeverity,
)
from core_engine.constraint_extractor import ConstraintExtractor, extract_constraints

# Risk scoring engine (kept - lightweight scoring)
from core_engine.risk_scoring_engine import (
    compute_risk_score,
    compute_batch_risk_scores,
    build_risk_clusters,
    build_anchors_from_enriched_files,
    compute_risk_summary,
    RiskScoreResult,
    RiskCluster,
    AnchorNode,
)

# Failure simulation engine (kept - deterministic failure chain generation)
from core_engine.failure_simulation_engine import (
    build_symbol_nodes_from_enriched_files,
    infer_edges,
    generate_failure_chains,
    simulate_propagation,
    run_failure_simulation,
    FailureChain,
    InferredEdge,
    SymbolNode,
)

# CI coverage gap detector (kept - lightweight analysis)
from core_engine.ci_coverage_gap_detector import (
    analyze_anchor,
    analyze_batch,
    generate_coverage_report,
    AnchorGapAnalysis,
    CoverageAxis,
)