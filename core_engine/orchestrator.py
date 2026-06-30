from schemas import AnalyzeRequest
from jinja2 import Environment, FileSystemLoader, Template  # pyright: ignore[reportMissingImports]
from api.models import persist_analysis_result
from language_adapters.python.python_adapter import AnalysisMode
from core_engine.risk_pattern_detector import RiskPatternDetector, detect_flows
from core_engine.failure_simulator import FailureSimulator
from core_engine.entrypoint_resolver import EntryPointResolver
from core_engine.file_exclusion import FileExclusionService
from core_engine.rir_compressor import RIRCompressor
from core_engine.behavior_extractor import extract_behavior_deltas
from core_engine.behavior_diff_builder import build_behavior_diffs
from core_engine.reachability_classifier import ReachabilityClassifier
from core_engine.side_effect_detector import SideEffectDetector
from core_engine.scenario_validator import score_scenarios, ValidationScore
from core_engine.causal_graph import (
    build_causal_graph,
    CausalGraph,
    CausalGraphBuilder,
    RepositorySymbolIndex,
)
from core_engine.behavior_delta_system import build_system_behavior_deltas, SystemBehaviorDelta
from core_engine.constraint_extractor import extract_constraints
from core_engine.constraint_types import ConstraintSet
from core_engine.change_influence import (
    build_change_influence,
    extract_changed_symbols,
    ChangeInfluence,
)
from core_engine.impact_evidence import (
    build_impact_evidence,
    extract_existing_edges_from_graph,
    ImpactEvidence,
    EvidenceCluster,
    EvidenceSummary,
    synthesize_evidence,
    synthesize_evidence_summary,
)
from core_engine.failure_archetype_engine import build_risk_hypotheses
from core_engine.llm_packet_compressor import build_llm_packet
from core_engine.risk_compressor import compress_risk_hypotheses
from typing import Any

# ══════════════════════════════════════════════════════════════════════════════
# DOMAIN RISK PRIORS (Layer 4 — Probabilistic Safety Net)
# ══════════════════════════════════════════════════════════════════════════════

# Base risk by domain (0.0–1.0)
_DOMAIN_BASE_RISK: dict[str, float] = {
    "billing": 0.7,
    "billing_core": 0.65,
    "billing_output": 0.6,
    "billing_calculation": 0.7,
    "billing_pricing": 0.6,
    "billing_cart": 0.6,
    "billing_recurring": 0.65,
    "money_movement": 0.8,
    "payment": 0.8,
    "order": 0.6,
    "invoice": 0.65,
    "tax": 0.7,
    "checkout": 0.75,
    "fulfillment": 0.5,
    "inventory": 0.5,
    "catalog": 0.4,
    "identity": 0.6,
    "auth": 0.6,
    "subscription": 0.65,
    "notification": 0.3,
    "cache": 0.2,
    "general": 0.2,
}

# Failure modes by domain
_DOMAIN_FAILURE_MODES: dict[str, list[str]] = {
    "billing": ["double_charge", "tax_mismatch", "ledger_drift"],
    "billing_core": ["double_charge", "partial_update_drift", "state_inconsistency"],
    "billing_output": ["rendering_drift", "financial_inconsistency"],
    "billing_calculation": ["tax_mismatch", "numeric_precision"],
    "billing_pricing": ["pricing_error", "discount_miscount"],
    "billing_cart": ["cart_state_drift", "price_mismatch"],
    "billing_recurring": ["subscription_cycle_error", "renewal_miscount"],
    "money_movement": ["double_charge", "ledger_drift", "irreversible_error"],
    "payment": ["double_charge", "payment_flow_error", "webhook_mismatch"],
    "order": ["idempotency_break", "duplicate_order", "order_state_drift"],
    "invoice": ["rendering_drift", "financial_inconsistency", "tax_mismatch"],
    "tax": ["tax_mismatch", "calculation_error", "compliance_violation"],
    "checkout": ["checkout_flow_break", "cart_state_drift", "payment_mismatch"],
    "fulfillment": ["fulfillment_delay", "inventory_desync"],
    "inventory": ["stock_desync", "oversell"],
    "catalog": ["catalog_desync", "price_stale"],
    "identity": ["auth_bypass_chain", "session_hijack"],
    "auth": ["auth_bypass_chain", "permission_escalation"],
    "subscription": ["subscription_cycle_error", "renewal_miscount", "access_control_break"],
    "notification": ["notification_silence", "delivery_delay"],
    "cache": ["stale_cache", "cache_invalidation_miss"],
    "general": ["state_inconsistency"],
}

# Mutation risk multipliers
_MUTATION_RISK: dict[str, float] = {
    "state_mutation": 0.6,
    "payment_flow_change": 0.8,
    "retry_handling_change": 0.75,
    "financial_calculation_change": 0.7,
    "schema_change": 0.5,
    "control_flow_change": 0.4,
    "api_contract_change": 0.55,
    "default": 0.3,
}


def _build_domain_risk_priors(
    change_influence: list[dict[str, Any]] | None = None,
    risk_patterns: list | None = None,
    enriched_files: list[dict] | None = None,
) -> dict[str, Any]:
    """Build domain_risk_priors from change influence and risk patterns.

    This is the Layer 4 probabilistic safety net that gives the LLM
    permission to flag risks even when the causal graph is sparse.
    """
    change_influence = change_influence or []
    risk_patterns = risk_patterns or []
    enriched_files = enriched_files or []

    # Collect domains touched by the change
    touched_domains: dict[str, float] = {}
    for ci in change_influence:
        domain = ci.get("domain", "general")
        score = ci.get("influence_score", 0.0)
        # Track max influence per domain
        if domain not in touched_domains or score > touched_domains[domain]:
            touched_domains[domain] = score

    # Also scan enriched files for domain signals
    for file_data in enriched_files:
        file_path = file_data.get("file_path", "").lower()
        keyword_signals = file_data.get("keyword_signals", [])
        for signal in keyword_signals:
            signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
            signal_lower = signal_text.lower()
            for domain_key in _DOMAIN_BASE_RISK:
                if domain_key in signal_lower or domain_key in file_path:
                    if domain_key not in touched_domains:
                        touched_domains[domain_key] = 0.5  # moderate signal from keywords

    # Build domain_risk_priors output
    domain_risk_priors: dict[str, Any] = {
        "domains": {},
        "mutation_risk": {},
        "overall_risk_level": "LOW",
    }

    # Populate domain entries
    for domain, base_risk in _DOMAIN_BASE_RISK.items():
        if domain in touched_domains:
            influence = touched_domains[domain]
            # Boost risk if change has high influence in this domain
            adjusted_risk = min(base_risk + influence * 0.2, 1.0)
            domain_risk_priors["domains"][domain] = {
                "base_risk": round(base_risk, 2),
                "adjusted_risk": round(adjusted_risk, 2),
                "touched_by_change": True,
                "change_influence": round(influence, 3),
                "failure_modes": _DOMAIN_FAILURE_MODES.get(domain, ["state_inconsistency"]),
            }

    # If no domains touched, include high-risk domains that might be relevant
    if not domain_risk_priors["domains"]:
        # Include a few high-risk domains as context
        for domain in ["billing", "payment", "order", "invoice", "tax"]:
            domain_risk_priors["domains"][domain] = {
                "base_risk": _DOMAIN_BASE_RISK.get(domain, 0.5),
                "adjusted_risk": _DOMAIN_BASE_RISK.get(domain, 0.5),
                "touched_by_change": False,
                "change_influence": 0.0,
                "failure_modes": _DOMAIN_FAILURE_MODES.get(domain, ["state_inconsistency"]),
            }

    # Populate mutation risk from risk patterns
    mutation_risks: dict[str, float] = {}
    for rp in risk_patterns:
        rp_dict = rp.model_dump() if hasattr(rp, "model_dump") else (rp if isinstance(rp, dict) else {})
        rp_type = rp_dict.get("risk_type", "")
        # Map risk pattern types to mutation risk categories
        if rp_type in ("FINANCIAL_LOGIC_CHANGE", "PAYMENT_FLOW"):
            mutation_risks["payment_flow_change"] = _MUTATION_RISK["payment_flow_change"]
        elif rp_type in ("TAX_CALCULATION_CHANGE",):
            mutation_risks["financial_calculation_change"] = _MUTATION_RISK["financial_calculation_change"]
        elif rp_type in ("SCHEMA_MIGRATION", "DATA_MODEL_CHANGE"):
            mutation_risks["schema_change"] = _MUTATION_RISK["schema_change"]
        elif rp_type in ("RETRY_HANDLING",):
            mutation_risks["retry_handling_change"] = _MUTATION_RISK["retry_handling_change"]
        elif rp_type in ("STATE_MUTATION",):
            mutation_risks["state_mutation"] = _MUTATION_RISK["state_mutation"]

    # Add default mutation risks if none detected
    if not mutation_risks:
        mutation_risks["state_mutation"] = _MUTATION_RISK["state_mutation"]

    domain_risk_priors["mutation_risk"] = mutation_risks

    # Compute overall risk level
    max_domain_risk = max(
        (d.get("adjusted_risk", 0.0) for d in domain_risk_priors["domains"].values()),
        default=0.0,
    )
    max_mutation_risk = max(mutation_risks.values(), default=0.0)
    overall = max(max_domain_risk, max_mutation_risk)

    if overall >= 0.7:
        domain_risk_priors["overall_risk_level"] = "HIGH"
    elif overall >= 0.5:
        domain_risk_priors["overall_risk_level"] = "MEDIUM"
    else:
        domain_risk_priors["overall_risk_level"] = "LOW"

    return domain_risk_priors

# failure_templates is an OPTIONAL hypothesis layer — imported lazily to allow
# graceful degradation if the module is unavailable or takes too long.
try:
    from core_engine.failure_templates import match_failure_templates
    _HAS_FAILURE_TEMPLATES = True
except ImportError:
    match_failure_templates = None  # type: ignore[assignment]
    _HAS_FAILURE_TEMPLATES = False


class BaseOrchestrator:
    def __init__(self, request, source, language, publisher=None, failure_simulation_llm=None):
        self.request = request
        self.source = source
        self.language = language
        self.publisher = publisher
        self.failure_simulation_llm = failure_simulation_llm

    def run_pr_analysis(self) -> dict[str, Any]:
        raise NotImplementedError("Must implement run_pr_analysis in subclass")

    def publish_comments(self, result: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError("Must implement publish_comments in subclass")

    async def log_run(self, result: dict[str, Any]) -> None:
        raise NotImplementedError("Must implement log_run in subclass")

    # -------------------------------------------------------------------------
    # Verdict Aggregator — LLM verdict primary, risk patterns secondary
    # -------------------------------------------------------------------------
    def _aggregate_verdict(
        self,
        failure_simulation: dict,
        validation_score: ValidationScore | None = None,
        risk_patterns: list | None = None,
    ) -> dict:
        """
        Aggregate verdict from LLM output and risk patterns.

        Core signal: LLM assessment with causal context.
        Secondary signal: risk patterns.
        """
        if not isinstance(failure_simulation, dict):
            failure_simulation = self._default_failure_simulation()

        llm_verdict = failure_simulation.get("verdict", "")

        # Accept LLM verdict if present
        if llm_verdict:
            return failure_simulation

        # Fall back to risk pattern-based verdict
        pr_risk_level = "LOW"
        if risk_patterns:
            pr_risk_level = "MEDIUM" if any(getattr(rp, 'severity', 'LOW') == 'HIGH' for rp in risk_patterns) else "LOW"
        
        failure_simulation["verdict"] = self._get_verdict(pr_risk_level, risk_patterns=risk_patterns)
        failure_simulation["verdict_rationale"] = (
            "No LLM verdict provided. Using risk pattern-based assessment."
        )

        return failure_simulation

    # -------------------------------------------------------------------------
    # Defaults and Normalization
    # -------------------------------------------------------------------------
    def _default_failure_simulation(self) -> dict:
        return {
            "failure_scenarios": [],
            "hidden_impact_chain": [],
            "checked_risk_areas": [],
            "missing_critical_tests": [],
            "broken_assumptions": [],
            "silent_failure_summary": "",
            "merge_risk_statement": "",
            "verdict_rationale": "",
            "verdict": "NO_SIGNIFICANT_PROPAGATION_FOUND",
            "final_question": "",
            "system_behavior_deltas": [],
            "matched_failure_templates": [],
        }

    def _normalize_failure_scenario(self, scenario: dict) -> dict:
        normalized_scenario = dict(scenario)
        normalized_scenario.setdefault("evidence_type", "inferred")
        normalized_scenario.setdefault("first_observable_signal", "unknown")
        normalized_scenario.setdefault("silent_failure", True)
        normalized_scenario.setdefault("ci_would_catch", False)
        normalized_scenario.setdefault("merge_risk_level", "MEDIUM")
        normalized_scenario.setdefault("false_confidence_reason", "")
        normalized_scenario.setdefault("why_it_slips_through", "")
        normalized_scenario.setdefault("merge_confidence_trap", "")
        normalized_scenario.setdefault("causal_chain", "")
        normalized_scenario.setdefault("failure_class", "")
        return normalized_scenario

    def _normalize_failure_simulation(self, failure_simulation: dict | list | None) -> dict:
        normalized = self._default_failure_simulation()

        if isinstance(failure_simulation, list):
            normalized["hidden_impact_chain"] = [str(item) for item in failure_simulation if str(item).strip()]
            return normalized

        if not isinstance(failure_simulation, dict):
            return normalized

        expected_keys = set(normalized.keys())
        for key in expected_keys:
            value = failure_simulation.get(key)
            if value is not None:
                normalized[key] = value

        for key, value in failure_simulation.items():
            if key in expected_keys:
                continue
            try:
                clean_key = key.encode().decode('unicode_escape')
            except (UnicodeDecodeError, AttributeError):
                clean_key = key
            clean_key = clean_key.strip().strip('"\'').strip()
            if clean_key in expected_keys:
                normalized[clean_key] = value

        normalized["failure_scenarios"] = [
            self._normalize_failure_scenario(scenario)
            for scenario in normalized.get("failure_scenarios", [])
            if isinstance(scenario, dict)
        ]
        normalized["hidden_impact_chain"] = [
            str(item) for item in normalized.get("hidden_impact_chain", []) if str(item).strip()
        ]
        normalized["checked_risk_areas"] = [
            str(item) for item in normalized.get("checked_risk_areas", []) if str(item).strip()
        ]
        normalized["missing_critical_tests"] = [
            str(item) for item in normalized.get("missing_critical_tests", []) if str(item).strip()
        ]
        normalized["broken_assumptions"] = [
            str(item) for item in normalized.get("broken_assumptions", []) if str(item).strip()
        ]

        return normalized

    def _sanitize_llm_output(self, raw_output: dict) -> dict:
        if not isinstance(raw_output, dict):
            return self._default_failure_simulation()

        sanitized = {}
        expected_keys = {
            "failure_scenarios",
            "hidden_impact_chain",
            "checked_risk_areas",
            "missing_critical_tests",
            "broken_assumptions",
            "silent_failure_summary",
            "merge_risk_statement",
            "verdict_rationale",
            "verdict",
            "final_question",
            "system_behavior_deltas",
            "matched_failure_templates",
        }

        for key, value in raw_output.items():
            try:
                clean_key = key.encode().decode('unicode_escape')
            except (UnicodeDecodeError, AttributeError):
                clean_key = key

            clean_key = clean_key.strip().strip('"\'').strip()

            matched_key = None
            for expected in expected_keys:
                if clean_key == expected or clean_key.replace(" ", "_").lower() == expected.lower():
                    matched_key = expected
                    break

            if matched_key:
                sanitized[matched_key] = value
            else:
                sanitized[clean_key] = value

        return sanitized

    # -------------------------------------------------------------------------
    # Risk Scoring (kept but demoted - was central signal, now supporting)
    # -------------------------------------------------------------------------
    def _calculate_file_risk_score(self, file_data: dict) -> float:
        lines_changed = file_data.get("lines_changed", 0)
        functions_changed = file_data.get("total_functions_changed", 0)
        num_endpoints = file_data.get("total_endpoints", 0)

        MAX_LINES = 20
        MAX_FUNCTIONS = 5

        normalized_lines = min(lines_changed / MAX_LINES, 1.0)
        normalized_functions = min(functions_changed / MAX_FUNCTIONS, 1.0)

        risk_score = (
            normalized_lines * 0.5 +
            normalized_functions * 0.3
        )
        risk_score *= (1 + 0.2 * num_endpoints)
        risk_score = min(risk_score, 1.0)

        return round(risk_score * 100, 2)

    def _calculate_pr_risk_score(self, files: list[dict]) -> float:
        if not files:
            return 0.0
        scores = [file["risk_score"] for file in files]
        max_score = max(scores)
        avg_score = sum(scores) / len(scores)
        return round(max_score * 0.6 + avg_score * 0.4, 2)

    def _classify_risk(self, score: float) -> str:
        RISK_LABELS = {
            "LOW": "🟢 LOW",
            "MEDIUM": "⚠️ MEDIUM",
            "HIGH": "🔥 HIGH"
        }
        if score < 20:
            return RISK_LABELS["LOW"]
        elif score < 50:
            return RISK_LABELS["MEDIUM"]
        else:
            return RISK_LABELS["HIGH"]

    def _get_verdict(self, pr_risk_level: str, risk_patterns: list | None = None) -> str:
        has_risk_patterns = bool(risk_patterns)
        if has_risk_patterns:
            if "HIGH" in pr_risk_level:
                return "BLOCK_REVIEW"
            return "REVIEW_REQUIRED"
        if "HIGH" in pr_risk_level:
            return "REVIEW_RECOMMENDED"
        if "MEDIUM" in pr_risk_level:
            return "REVIEW_REQUIRED"
        return "SAFE_TO_MERGE"

    def _render_pr_comment(self, template_name: str, result: dict) -> str:
        env = Environment(loader=FileSystemLoader("templates"))
        jinja_template: Template = env.get_template(template_name)
        failure_simulation = self._normalize_failure_simulation(
            result.get("failure_simulation")
        )
        return jinja_template.render(
            verdict=result.get("verdict", "UNKNOWN"),
            failure_simulation=failure_simulation,
        )

    def _enrich_file(
        self,
        file: dict,
        changed_functions: list,
        endpoints: list | None = None,
        keyword_signals: list | None = None,
    ) -> dict:
        endpoints = endpoints or []
        keyword_signals = keyword_signals or []

        enriched_file = {
            "file_path": file["file_path"],
            "lines_changed": file["lines_changed"],
            "hunks": file.get("hunks", []),
            "total_functions_changed": len(changed_functions),
            "total_endpoints": len(endpoints),
            "total_keyword_signals": len(keyword_signals),
            "changed_functions": changed_functions,
            "endpoints": endpoints,
            "keyword_signals": keyword_signals,
        }
        enriched_file["flows"] = detect_flows(enriched_file)
        enriched_file["risk_score"] = self._calculate_file_risk_score(enriched_file)
        enriched_file["risk_level"] = self._classify_risk(enriched_file["risk_score"])
        return enriched_file

    def _build_result(
        self,
        repo: str,
        pr_number: int,
        analysis_mode: AnalysisMode,
        enriched_files: list[dict],
        risk_patterns: list | None = None,
        failure_simulation: dict | list | None = None,
        compressed_for_llm: dict | None = None,
        change_influence: list[dict] | None = None,
        impact_evidence: list[dict] | None = None,
        risk_zones: list[str] | None = None,
        changed_symbols: list[str] | None = None,
        risk_hypotheses: list[dict] | None = None,
        risk_anchors: list[dict] | None = None,
        side_effects: list[dict] | None = None,
        constraints: list[dict] | None = None,
        business_objects: list[dict] | None = None,
    ) -> dict:
        """Build result with only analyser outputs.
        
        Returns only the outputs from the evidence analyzers, not intermediate
        processing data like failure_simulation or compressed_for_llm.
        """
        return {
            "repo": repo,
            "pr_number": pr_number,
            "changed_symbols": changed_symbols or [],
            "risk_anchors": risk_anchors or [],
            "impact_evidence": impact_evidence or [],
            "side_effects": side_effects or [],
            "constraints": constraints or [],
            "business_objects": business_objects or [],
            "change_influence": change_influence or [],
            "risk_zones": risk_zones or ["general"],
        }

    def _build_repo_index(
        self,
        files: list[tuple[str, str]] | None = None,
    ) -> RepositorySymbolIndex | None:
        """Build a RepositorySymbolIndex from (file_path, content) pairs.

        Decoupled from any specific source adapter — the orchestrator may
        feed in snapshots it already fetched (FULL_FILE mode) or pass
        `None` to disable the repo-wide expansion (DIFF_ONLY mode).

        Defensive: returns `None` on any error so the rest of the
        pipeline keeps running with the existing diff-only behavior.
        """
        if not files:
            return None
        try:
            return RepositorySymbolIndex.from_files(files)
        except Exception as exc:
            print(f"Repo index build failed (non-fatal): {exc!r}")
            return None

    def _match_failure_templates(
        self,
        risk_patterns: list,
        enriched_files: list[dict],
        behavior_diffs: list[Any] | None = None,
    ) -> list[dict]:
        """
        Match failure templates if available. Returns empty list if templates
        module is not available — failure templates are OPTIONAL.
        """
        if not _HAS_FAILURE_TEMPLATES or match_failure_templates is None:
            return []
        try:
            return match_failure_templates(
                risk_patterns=risk_patterns,
                enriched_files=enriched_files,
                behavior_diffs=behavior_diffs,
            )
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # Shared causal pipeline
    # -------------------------------------------------------------------------
    def _run_causal_pipeline(
        self,
        enriched_files: list[dict],
        risk_patterns: list,
        behavior_diffs: list,
        compressed_for_llm: dict,
        repo_index: RepositorySymbolIndex | None = None,
        entry_points_affected: list | None = None,
    ) -> tuple[CausalGraph, list[dict], list[Any], list[str]]:
        """Run the causal graph + templates pipeline.

        Args:
            enriched_files: Diff-only or full-file enriched file data.
            risk_patterns: Detected risk patterns.
            behavior_diffs: Behavior-level deltas.
            compressed_for_llm: Compressed IR for the LLM.
            repo_index: Optional repo-wide symbol index.

        Returns:
            Tuple of (causal_graph, template_matches, system_deltas, directly_changed).
        """
        # Step 1: Build causal graph
        causal_graph = build_causal_graph(
            enriched_files=enriched_files,
            behavior_diffs=behavior_diffs,
            repo_index=repo_index,
        )

        # Step 2: Extract directly changed symbols
        directly_changed = list({
            diff.symbol for diff in behavior_diffs
        }) if behavior_diffs else []

        # Step 3: Match failure templates (OPTIONAL hypothesis layer)
        template_matches = self._match_failure_templates(
            risk_patterns=risk_patterns,
            enriched_files=enriched_files,
            behavior_diffs=behavior_diffs,
        )

        # Step 4: Build system-level behavior deltas
        system_deltas = build_system_behavior_deltas(
            enriched_files=enriched_files,
            behavior_diffs=behavior_diffs,
            causal_graph=causal_graph,
            failure_template_matches=template_matches,
        )

        return causal_graph, template_matches, system_deltas, directly_changed

    def _build_impact_evidence(
        self,
        changed_symbols_list: list[dict[str, str]],
        causal_graph: CausalGraph | None = None,
    ) -> list[dict[str, Any]]:
        """Build impact evidence from changed symbols.

        Args:
            changed_symbols_list: List of {symbol, file} dicts.
            causal_graph: Optional causal graph to avoid duplicating edges.

        Returns:
            List of impact evidence dicts.
        """
        existing_edges = extract_existing_edges_from_graph(causal_graph)
        evidence_list = build_impact_evidence(
            all_changed_symbols=changed_symbols_list,
            existing_edges=existing_edges,
        )
        return [ev.to_dict() for ev in evidence_list]

    def _run_llm_with_causal_context(
        self,
        compressed_for_llm: dict[str, Any],
        causal_graph: CausalGraph,
        system_constraints: ConstraintSet | None = None,
        behavior_diffs: list[Any] | None = None,
        enriched_files: list[dict] | None = None,
        risk_patterns: list | None = None,
    ) -> dict:
        """Call LLM with the V6 evidence-driven LLM payload."""
        assert self.failure_simulation_llm is not None, (
            "failure_simulation_llm must be set before calling _run_llm_with_causal_context"
        )

        # Build changed symbols list
        changed_symbols_list = extract_changed_symbols(
            behavior_diffs=behavior_diffs,
            enriched_files=enriched_files,
        )
        changed_symbols = [
            item["symbol"] for item in changed_symbols_list
            if isinstance(item, dict) and item.get("symbol")
        ]

        # Layer 1: change_influence — scored symbols + domains
        change_influence_entries = build_change_influence(
            all_changed_symbols=changed_symbols_list,
        )
        change_influence = [entry.to_dict() for entry in change_influence_entries]

        # Layer 2: impact_evidence — evidence connecting changed symbols
        impact_evidence = self._build_impact_evidence(
            changed_symbols_list=changed_symbols_list,
            causal_graph=causal_graph,
        )

        # Layer 2a: synthesize evidence summary for risk hypotheses builder
        evidence_summary = self._synthesize_evidence_summary(impact_evidence)

        # Layer 3: risk_zones — domain regions
        risk_zones = self._build_minimal_system_context(
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
            causal_graph=causal_graph,
        ).get("regions", ["general"])

        # Layer 4: Build risk_hypotheses (unified replacement for both evidence_summary + failure_archetypes)
        risk_hypotheses = build_risk_hypotheses(
            change_influence=change_influence,
            evidence_summary=evidence_summary,
        )

        # Compress risk hypotheses and add to compressed_for_llm
        compressed_risk_hypotheses = compress_risk_hypotheses(
            risk_hypotheses=risk_hypotheses,
            top_n=3,
            compress_for_llm=True,
        )
        compressed_for_llm["compressed_risk_hypotheses"] = compressed_risk_hypotheses

        # Call LLM with ONLY the parameters it accepts
        # Map compressed_for_llm content to LLM.generate() signature
        output = self.failure_simulation_llm.generate(
            repo=compressed_for_llm.get("repo", ""),
            pr_number=compressed_for_llm.get("pr_number", 0),
            change_influence=compressed_for_llm.get("change_influence"),
            impact_evidence=compressed_for_llm.get("impact_evidence"),
            risk_zones=compressed_for_llm.get("risk_zones"),
            changed_symbols=compressed_for_llm.get("changed_symbols"),
            evidence_summary=compressed_risk_hypotheses,  # compressed risk hypotheses as evidence_summary
        )
        failure_simulation = output.model_dump()

        # Sanitize LLM output
        failure_simulation = self._sanitize_llm_output(failure_simulation)

        # Score scenarios (not hard-reject)
        validation_score = score_scenarios(failure_simulation, compressed_for_llm)
        if validation_score.warnings:
            for warning in validation_score.warnings:
                print(f"Scenario validation warning: {warning}")
        if validation_score.notes:
            for note in validation_score.notes:
                print(f"Scenario validation note: {note}")

        # Apply confidence adjustments
        for score in validation_score.scenarios:
            if score.scenario_index < len(failure_simulation.get("failure_scenarios", [])):
                scenario = failure_simulation["failure_scenarios"][score.scenario_index]
                orig_confidence = scenario.get("confidence", 0.7)
                scenario["confidence"] = round(orig_confidence * score.confidence_adjustment, 3)
                if score.issues:
                    scenario["reasoning"] = (
                        scenario.get("reasoning", "") +
                        f"\n[Validation: {'; '.join(score.issues)}]"
                    )

        return failure_simulation

    def _build_minimal_system_context(
        self,
        enriched_files: list[dict] | None = None,
        risk_patterns: list | None = None,
        causal_graph: Any = None,
    ) -> dict[str, Any]:
        """Build minimal system_context with only regions (risk_zones)."""
        regions = set()
        
        # Extract regions from enriched files
        if enriched_files:
            for file_data in enriched_files:
                file_path = file_data.get("file_path", "").lower()
                keyword_signals = file_data.get("keyword_signals", [])
                
                # Domain detection from file path
                for domain in ["checkout", "order", "invoice", "tax", "payment", "billing", "auth", "fulfillment", "inventory", "catalog"]:
                    if domain in file_path:
                        regions.add(domain)
                
                # Domain detection from keyword signals
                for signal in keyword_signals:
                    signal_text = signal.keyword if hasattr(signal, "keyword") else str(signal)
                    signal_lower = signal_text.lower()
                    for domain in ["checkout", "order", "invoice", "tax", "payment", "billing", "auth", "fulfillment", "inventory", "catalog"]:
                        if domain in signal_lower:
                            regions.add(domain)
        
        # Extract regions from risk patterns
        if risk_patterns:
            for rp in risk_patterns:
                rp_dict = rp.model_dump() if hasattr(rp, "model_dump") else (rp if isinstance(rp, dict) else {})
                domain = rp_dict.get("domain", "")
                if domain and domain != "general":
                    regions.add(domain)
        
        # Extract regions from causal graph nodes
        if causal_graph and hasattr(causal_graph, "nodes"):
            for node_name, node in causal_graph.nodes.items():
                node_type = getattr(node, "node_type", "")
                if node_type in ("endpoint", "service"):
                    # Extract domain from node name or metadata
                    node_lower = node_name.lower()
                    for domain in ["checkout", "order", "invoice", "tax", "payment", "billing", "auth"]:
                        if domain in node_lower:
                            regions.add(domain)
        
        return {
            "regions": sorted(list(regions)) if regions else ["general"]
        }

    def _finalize_verdict(
        self,
        failure_simulation: dict,
        validation_score: ValidationScore,
        risk_patterns: list | None = None,
    ) -> dict:
        """Aggregate verdict using LLM output and risk patterns."""
        return self._aggregate_verdict(
            failure_simulation=failure_simulation,
            validation_score=validation_score,
            risk_patterns=risk_patterns,
        )

    def _synthesize_evidence_summary(
        self,
        impact_evidence: list[dict],
    ) -> list[dict]:
        """Synthesize evidence into summary clusters for the LLM packet.

        Instead of N×M raw evidence records, produce synthesized evidence
        summaries grouped by theme. The deterministic engine answers
        "what appears involved?" before the LLM sees anything.
        """
        # Convert dicts back to ImpactEvidence objects for the synthesizer
        from core_engine.impact_evidence import ImpactEvidence as ImpactEvidenceClass
        evidence_objects = []
        for ev in impact_evidence:
            evidence_objects.append(ImpactEvidenceClass(
                source_symbol=ev.get("source_symbol", ""),
                target_symbol=ev.get("target_symbol", ""),
                evidence_type=ev.get("evidence_type", "canonical_flow"),
                confidence=ev.get("confidence", 0.2),
                explanation=ev.get("explanation", ""),
            ))

        # Synthesize into summaries
        summaries = synthesize_evidence_summary(evidence_objects)
        return [s.to_dict() for s in summaries]

class Orchestrator(BaseOrchestrator):
    """Repo-aware orchestrator using GitHub PR diff + full file snapshots."""

    def __init__(self, request: AnalyzeRequest, source, language, publisher=None, failure_simulation_llm=None):
        super().__init__(request, source, language, publisher, failure_simulation_llm)

    def run_pr_analysis(self) -> dict[str, Any]:
        request, source, lang = self.request, self.source, self.language

        diff_ir = source.fetch_diff(request.repo, request.pr_number)
        file_exclusion = FileExclusionService()
        excluded_files = []
        kept_files = []
        for file in diff_ir.files:
            file_path = getattr(file, "file_path", "")
            matched = file_exclusion.get_exclusion_match(file_path)
            if matched:
                excluded_files.append({"file_path": file_path, "reason": f"matched {matched}"})
                continue
            kept_files.append(file)
        diff_ir.files = kept_files

        sha = source.get_head_sha(request.repo, request.pr_number)

        files = lang.extract_changed_files(diff_ir) or []
        enriched_files = []
        repo_index_files: list[tuple[str, str]] = []

        for file in files:
            print(f"Processing file in FULL_FILE mode: {file['file_path']}")
            snapshot = source.fetch_file_at_sha(
                repo=request.repo, file_path=file["file_path"], sha=sha,
            )
            changed_functions = lang.extract_changed_functions(
                file=file, mode=AnalysisMode.FULL_FILE, content=snapshot.content,
            )
            keyword_signals = lang.extract_keyword_signals_from_diff(file=file)
            endpoints = lang.extract_endpoints(
                file_path=file["file_path"], content=snapshot.content,
            )
            changed_function_names = {fn.name for fn in changed_functions}
            impacted_endpoints = [
                ep for ep in endpoints if ep["function"] in changed_function_names
            ]
            enriched_files.append(self._enrich_file(
                file=file, changed_functions=changed_functions,
                endpoints=impacted_endpoints, keyword_signals=keyword_signals,
            ))
            repo_index_files.append((file["file_path"], snapshot.content))

        repo_index = self._build_repo_index(repo_index_files)

        risk_detector = RiskPatternDetector()
        risk_patterns = risk_detector.detect(enriched_files)
        resolver = EntryPointResolver()
        entry_points_affected = resolver.resolve(enriched_files, risk_patterns)
        system_impact = resolver.resolve_system_impact(risk_patterns, entry_points_affected)

        behavior_deltas = extract_behavior_deltas(enriched_files, risk_patterns)
        behavior_diffs = build_behavior_diffs(enriched_files)
        reachability_classifier = ReachabilityClassifier()
        reachability_results = reachability_classifier.classify_batch(enriched_files)
        side_effect_detector = SideEffectDetector()
        side_effect_results = side_effect_detector.detect(enriched_files)

        compressor = RIRCompressor()
        compressed_for_llm = compressor.compress_v3(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected, behavior_diffs=behavior_diffs,
        )

        # Run causal pipeline (causal graph + templates + behavior deltas)
        causal_graph, template_matches, system_deltas, directly_changed = self._run_causal_pipeline(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            behavior_diffs=behavior_diffs, compressed_for_llm=compressed_for_llm,
            repo_index=repo_index,
            entry_points_affected=entry_points_affected,
        )

        try:
            if self.failure_simulation_llm:
                print("Calling LLM...")
                failure_simulation = self._run_llm_with_causal_context(
                    compressed_for_llm=compressed_for_llm,
                    causal_graph=causal_graph,
                    behavior_diffs=behavior_diffs,
                    enriched_files=enriched_files,
                    risk_patterns=risk_patterns,
                )
                # Finalize verdict
                validation_score = score_scenarios(failure_simulation, compressed_for_llm)
                failure_simulation = self._finalize_verdict(
                    failure_simulation=failure_simulation,
                    validation_score=validation_score,
                    risk_patterns=risk_patterns,
                )
            else:
                failure_simulation = self._default_failure_simulation()
                failure_scenario_lines = FailureSimulator().generate(risk_patterns, enriched_files)
                failure_simulation["failure_scenarios"] = [
                    {"title": line, "evidence_type": "inferred", "silent_failure": True, "merge_risk_level": "MEDIUM"}
                    for line in failure_scenario_lines
                ]
                failure_simulation["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
                failure_simulation["matched_failure_templates"] = template_matches

        except Exception as e:
            print(f"LLM failure simulation failed, falling back to rules: {repr(e)}")
            failure_simulation = self._default_failure_simulation()
            failure_scenario_lines = FailureSimulator().generate(risk_patterns, enriched_files)
            failure_simulation["failure_scenarios"] = [
                {"title": line, "evidence_type": "inferred", "silent_failure": True, "merge_risk_level": "MEDIUM"}
                for line in failure_scenario_lines
            ]
            failure_simulation["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
            failure_simulation["matched_failure_templates"] = template_matches

        # Pre-compute causal signals for _build_result
        changed_symbols_list = extract_changed_symbols(
            behavior_diffs=behavior_diffs,
            enriched_files=enriched_files,
        )
        changed_symbols = [
            item["symbol"] for item in changed_symbols_list
            if isinstance(item, dict) and item.get("symbol")
        ]
        change_influence_entries = build_change_influence(
            all_changed_symbols=changed_symbols_list,
        )
        change_influence = [entry.to_dict() for entry in change_influence_entries]
        impact_evidence = self._build_impact_evidence(
            changed_symbols_list=changed_symbols_list,
            causal_graph=causal_graph,
        )
        risk_zones = self._build_minimal_system_context(
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
            causal_graph=causal_graph,
        ).get("regions", ["general"])

        # Build unified risk_hypotheses from impact evidence and change influence
        evidence_summary = self._synthesize_evidence_summary(impact_evidence)
        risk_hypotheses = build_risk_hypotheses(
            change_influence=change_influence,
            evidence_summary=evidence_summary,
        )

        # Compress risk hypotheses into families for LLM context
        compressed_risk_hypotheses = compress_risk_hypotheses(
            risk_hypotheses=risk_hypotheses,
            top_n=3,
            compress_for_llm=True,
        )
        compressed_for_llm["compressed_risk_hypotheses"] = compressed_risk_hypotheses

        data = self._build_result(
            repo=request.repo,
            pr_number=request.pr_number,
            analysis_mode=AnalysisMode.FULL_FILE,
            enriched_files=enriched_files,
            changed_symbols=changed_symbols,
            risk_anchors=[rp.model_dump() if hasattr(rp, "model_dump") else rp for rp in risk_patterns],
            impact_evidence=impact_evidence,
            side_effects=side_effect_results if side_effect_results else [],
            constraints=[],
            business_objects=[],
            change_influence=change_influence,
            risk_zones=risk_zones,
        )

        return data

    def publish_comments(self, result: dict[str, Any]) -> None:
        comment = self._render_pr_comment("github/pr_comment.md.j2", result)
        result["generated_comment"] = comment
        print(f"Publishing comment to {self.request.repo} PR #{self.request.pr_number}:\n{comment}")

    async def log_run(self, result: dict[str, Any]) -> None:
        await persist_analysis_result(result)
        print(f"Logged analysis run for {self.request.repo} PR #{self.request.pr_number}")


class DiffOrchestrator(BaseOrchestrator):
    """Demo-safe orchestrator using raw diff text (no repo access)."""

    def __init__(self, request: dict, source, language, publisher=None, failure_simulation_llm=None):
        super().__init__(request, source, language, publisher, failure_simulation_llm)

    def run_pr_analysis(self) -> dict[str, Any]:
        request, source, lang = self.request, self.source, self.language

        diff_text = request.get("diff") or ""
        diff_ir = source._format_diff(diff_text)
        file_exclusion = FileExclusionService()
        excluded_files = []
        kept_files = []
        for file in diff_ir.files:
            file_path = getattr(file, "file_path", "")
            matched = file_exclusion.get_exclusion_match(file_path)
            if matched:
                excluded_files.append({"file_path": file_path, "reason": f"matched {matched}"})
                continue
            kept_files.append(file)
        diff_ir.files = kept_files

        files = lang.extract_changed_files(diff_ir) or []
        enriched_files = []

        for file in files:
            print(f"Processing file in DIFF_ONLY mode: {file['file_path']}")
            changed_functions = lang.extract_changed_functions(
                file=file, mode=AnalysisMode.DIFF_ONLY,
            )
            keyword_signals = lang.extract_keyword_signals_from_diff(file=file)
            endpoints = lang.extract_endpoints_from_diff_only(file=file)
            changed_function_names = {fn.name for fn in changed_functions}
            impacted_endpoints = [
                ep for ep in endpoints if ep["function"] in changed_function_names
            ]
            enriched_files.append(self._enrich_file(
                file=file, changed_functions=changed_functions,
                endpoints=impacted_endpoints, keyword_signals=keyword_signals,
            ))

        risk_detector = RiskPatternDetector()
        risk_patterns = risk_detector.detect(enriched_files)
        resolver = EntryPointResolver()
        entry_points_affected = resolver.resolve(enriched_files, risk_patterns)
        system_impact = resolver.resolve_system_impact(risk_patterns, entry_points_affected)

        behavior_deltas = extract_behavior_deltas(enriched_files, risk_patterns)
        behavior_diffs = build_behavior_diffs(enriched_files)
        reachability_classifier = ReachabilityClassifier()
        reachability_results = reachability_classifier.classify_batch(enriched_files)
        side_effect_detector = SideEffectDetector()
        side_effect_results = side_effect_detector.detect(enriched_files)

        compressor = RIRCompressor()
        compressed_for_llm = compressor.compress_v3(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected, behavior_diffs=behavior_diffs,
        )

        # Run causal pipeline
        causal_graph, template_matches, system_deltas, directly_changed = self._run_causal_pipeline(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            behavior_diffs=behavior_diffs, compressed_for_llm=compressed_for_llm,
            entry_points_affected=entry_points_affected,
        )

        try:
            if self.failure_simulation_llm:
                print("Calling LLM with V6 evidence-driven input contract...")
                failure_simulation = self._run_llm_with_causal_context(
                    compressed_for_llm=compressed_for_llm,
                    causal_graph=causal_graph,
                    behavior_diffs=behavior_diffs,
                    enriched_files=enriched_files,
                    risk_patterns=risk_patterns,
                )
                # Finalize verdict
                validation_score = score_scenarios(failure_simulation, compressed_for_llm)
                failure_simulation = self._finalize_verdict(
                    failure_simulation=failure_simulation,
                    validation_score=validation_score,
                    risk_patterns=risk_patterns,
                )
            else:
                failure_simulation = self._default_failure_simulation()
                failure_scenario_lines = FailureSimulator().generate(risk_patterns, enriched_files)
                failure_simulation["failure_scenarios"] = [
                    {"title": line, "evidence_type": "inferred", "silent_failure": True, "merge_risk_level": "MEDIUM"}
                    for line in failure_scenario_lines
                ]
                failure_simulation["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
                failure_simulation["matched_failure_templates"] = template_matches

        except Exception as e:
            print(f"LLM failure simulation failed, falling back to rules: {repr(e)}")
            failure_simulation = self._default_failure_simulation()
            failure_scenario_lines = FailureSimulator().generate(risk_patterns, enriched_files)
            failure_simulation["failure_scenarios"] = [
                {"title": line, "evidence_type": "inferred", "silent_failure": True, "merge_risk_level": "MEDIUM"}
                for line in failure_scenario_lines
            ]
            failure_simulation["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
            failure_simulation["matched_failure_templates"] = template_matches

        # Pre-compute causal signals for _build_result
        changed_symbols_list = extract_changed_symbols(
            behavior_diffs=behavior_diffs,
            enriched_files=enriched_files,
        )
        changed_symbols = [
            item["symbol"] for item in changed_symbols_list
            if isinstance(item, dict) and item.get("symbol")
        ]
        change_influence_entries = build_change_influence(
            all_changed_symbols=changed_symbols_list,
        )
        change_influence = [entry.to_dict() for entry in change_influence_entries]
        impact_evidence = self._build_impact_evidence(
            changed_symbols_list=changed_symbols_list,
            causal_graph=causal_graph,
        )
        risk_zones = self._build_minimal_system_context(
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
            causal_graph=causal_graph,
        ).get("regions", ["general"])

        # Build unified risk_hypotheses from impact evidence and change influence
        evidence_summary = self._synthesize_evidence_summary(impact_evidence)
        risk_hypotheses = build_risk_hypotheses(
            change_influence=change_influence,
            evidence_summary=evidence_summary,
        )

        # Compress risk hypotheses into families for LLM context
        compressed_risk_hypotheses = compress_risk_hypotheses(
            risk_hypotheses=risk_hypotheses,
            top_n=3,
            compress_for_llm=True,
        )
        compressed_for_llm["compressed_risk_hypotheses"] = compressed_risk_hypotheses

        data = self._build_result(
            repo=request.get("repo", "example/repo"),
            pr_number=request.get("pr_number", 1),
            analysis_mode=AnalysisMode.DIFF_ONLY,
            enriched_files=enriched_files,
            changed_symbols=changed_symbols,
            risk_anchors=[rp.model_dump() if hasattr(rp, "model_dump") else rp for rp in risk_patterns],
            impact_evidence=impact_evidence,
            side_effects=side_effect_results if side_effect_results else [],
            constraints=[],
            business_objects=[],
            change_influence=change_influence,
            risk_zones=risk_zones,
        )

        return data

    def publish_comments(self, result: dict[str, Any]) -> dict[str, Any]:
        comment = self._render_pr_comment("github/pr_comment.md.j2", result)
        result["generated_comment"] = comment
        print(comment)
        return result

    async def log_run(self, result: dict[str, Any]) -> None:
        await persist_analysis_result(result)
        print(f"Logged analysis run for {result.get('repo', 'example/repo')} PR #{result.get('pr_number', 1)}")