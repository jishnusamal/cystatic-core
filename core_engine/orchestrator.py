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
from core_engine.propagation_engine import build_impact_tree, ImpactTree
from core_engine.behavior_delta_system import build_system_behavior_deltas, SystemBehaviorDelta

# failure_templates is an OPTIONAL hypothesis layer — imported lazily to allow
# graceful degradation if the module is unavailable or takes too long.
# Core signals (blast radius, causal graph, impact tree) do NOT depend on it.
try:
    from core_engine.failure_templates import match_failure_templates
    _HAS_FAILURE_TEMPLATES = True
except ImportError:
    match_failure_templates = None  # type: ignore[assignment]
    _HAS_FAILURE_TEMPLATES = False
from typing import Any


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
    # Verdict Aggregator — blast radius is primary, templates are optional
    # -------------------------------------------------------------------------
    def _aggregate_verdict(
        self,
        failure_simulation: dict,
        validation_score: ValidationScore | None = None,
        impact_tree: ImpactTree | None = None,
        risk_patterns: list | None = None,
    ) -> dict:
        """
        Aggregate verdict from blast radius propagation and LLM output.

        Core signal: blast radius from causal graph propagation.
        Secondary signal: LLM assessment.
        Optional hypothesis: failure templates (demoted — conclusions, not evidence).

        matched_failure_templates are treated as optional hypotheses, not core signals.
        They do NOT drive verdict upgrades. Only blast radius propagation does.
        """
        if not isinstance(failure_simulation, dict):
            failure_simulation = self._default_failure_simulation()

        llm_verdict = failure_simulation.get("verdict", "")
        has_impact = impact_tree is not None and bool(impact_tree.get_impacted_symbols(min_confidence=0.2))

        # Get blast radius from impact tree as the primary signal
        blast_radius = impact_tree.get_blast_radius() if impact_tree else {}
        max_confidence = blast_radius.get("max_confidence", 0.0)
        impacted_services = blast_radius.get("impacted_services", [])
        impacted_endpoints = blast_radius.get("impacted_endpoints", [])
        impacted_databases = blast_radius.get("impacted_databases", [])

        # Blast radius drives verdict
        if impacted_services or impacted_endpoints or impacted_databases:
            # There is actual blast radius - always at least LOW_RISK
            blast_based_verdict = "LOW_RISK"
            blast_rationale_parts = []

            if impacted_services:
                blast_rationale_parts.append(
                    f"affects services: {', '.join(impacted_services)}"
                )
            if impacted_endpoints:
                blast_rationale_parts.append(
                    f"affects endpoints: {', '.join(impacted_endpoints)}"
                )
            if impacted_databases:
                blast_rationale_parts.append(
                    f"affects datastores: {', '.join(impacted_databases)}"
                )

            if max_confidence >= 0.6:
                blast_based_verdict = "REVIEW_REQUIRED"
            elif max_confidence >= 0.25:
                blast_based_verdict = "UNCERTAIN_IMPACT"

            # Check LLM verdict — only allow STRONG llm verdicts to override
            # (LLM sees code context we don't have from graph alone)
            strong_llm_verdicts = {"SAFE", "BLOCK_REVIEW"}
            if llm_verdict in strong_llm_verdicts:
                failure_simulation["verdict"] = llm_verdict
                failure_simulation["verdict_rationale"] = (
                    f"Blast radius detection suggests {blast_based_verdict} "
                    f"({'; '.join(blast_rationale_parts)}), "
                    f"but LLM overrode with {llm_verdict} based on code-level analysis."
                )
                return failure_simulation

            failure_simulation["verdict"] = blast_based_verdict
            failure_simulation["verdict_rationale"] = (
                f"Blast radius analysis: {'; '.join(blast_rationale_parts)}. "
                f"Max propagation confidence: {max_confidence:.2f}. "
                f"Verdict: {blast_based_verdict}."
            )
            return failure_simulation

        # No significant blast radius detected — fall back to LLM
        if llm_verdict:
            return failure_simulation

        # Default when nothing detected
        failure_simulation["verdict"] = "NO_SIGNIFICANT_PROPAGATION_FOUND"
        failure_simulation["verdict_rationale"] = (
            "No downstream propagation detected through the causal graph. "
            "Changes appear isolated."
        )

        return failure_simulation

    # -------------------------------------------------------------------------
    # Defaults and Normalization
    # -------------------------------------------------------------------------
    def _default_failure_simulation(self) -> dict:
        # SAFE is no longer the default - NO_SIGNIFICANT_PROPAGATION_FOUND is
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
            "blast_radius": {},
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
        normalized_scenario.setdefault("hop_confidence", 1.0)
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
            "blast_radius",
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
        entry_points_affected: list | None = None,
        system_impact: list | None = None,
        excluded_files: list[dict] | None = None,
        compressed_for_llm: dict | None = None,
    ) -> dict:
        failure_simulation = self._normalize_failure_simulation(failure_simulation)
        pr_risk_score = self._calculate_pr_risk_score(enriched_files)
        pr_risk_level = self._classify_risk(pr_risk_score)

        keywords_detected = [
            signal
            for file in enriched_files
            for signal in file.get("keyword_signals", [])
        ]

        # Accept the full new verdict set
        llm_verdict = None
        if isinstance(failure_simulation, dict):
            llm_verdict = failure_simulation.get("verdict")

        allowed_llm_verdicts = {
            "SAFE", "LOW_RISK", "UNCERTAIN_IMPACT",
            "NO_SIGNIFICANT_PROPAGATION_FOUND", "REVIEW_REQUIRED", "BLOCK_REVIEW",
        }
        final_verdict = (
            llm_verdict
            if llm_verdict in allowed_llm_verdicts
            else self._get_verdict(pr_risk_level, risk_patterns=risk_patterns)
        )

        return {
            "repo": repo,
            "pr_number": pr_number,
            "analysis_mode": analysis_mode.value,
            "files": enriched_files,
            "excluded_files": excluded_files or [],
            "keywords_detected": keywords_detected,
            "risk_patterns": [
                rp.model_dump() if hasattr(rp, "model_dump") else rp
                for rp in (risk_patterns or [])
            ],
            "failure_simulation": failure_simulation,
            "entry_points_affected": [
                ep.model_dump() if hasattr(ep, "model_dump") else ep
                for ep in (entry_points_affected or [])
            ],
            "compressed_for_llm": compressed_for_llm or {},
            "system_impact": [
                impact.model_dump() if hasattr(impact, "model_dump") else impact
                for impact in (system_impact or [])
            ],
            "pr_risk_score": pr_risk_score,
            "pr_risk_level": pr_risk_level,
            "verdict": final_verdict,
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

        Core signals (blast radius, causal graph, impact tree) do NOT depend on this.
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
    ) -> tuple[Any, Any, list[dict], list[Any], list[str], list]:
        """Run the causal graph + propagation engine + templates pipeline.

        Args:
            enriched_files: Diff-only or full-file enriched file data.
            risk_patterns: Detected risk patterns.
            behavior_diffs: Behavior-level deltas.
            compressed_for_llm: Compressed IR for the LLM.
            repo_index: Optional repo-wide symbol index. When provided, the
                causal graph expands `known_symbols` to include every
                defined function in the repo and registers ALL endpoints —
                not just the ones in the diff. This is the repo-wide
                expansion that unlocks richer blast radius propagation.
                Pass `None` in DIFF_ONLY mode (no repo access).
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

        # Step 3: Build impact tree (propagation engine)
        impact_tree = build_impact_tree(
            causal_graph=causal_graph,
            directly_changed=directly_changed,
            max_hops=5,
        )

        # Step 4: Match failure templates (OPTIONAL hypothesis layer)
        template_matches = self._match_failure_templates(
            risk_patterns=risk_patterns,
            enriched_files=enriched_files,
            behavior_diffs=behavior_diffs,
        )

        # Step 5: Build system-level behavior deltas
        system_deltas = build_system_behavior_deltas(
            enriched_files=enriched_files,
            behavior_diffs=behavior_diffs,
            causal_graph=causal_graph,
            failure_template_matches=template_matches,
        )

        # Step 6: Build structured hypotheses on causal edges (replaces unknowns dump zone)
        structured_hypotheses = self._build_structured_hypotheses(
            causal_graph=causal_graph,
            impact_tree=impact_tree,
            risk_patterns=risk_patterns,
            template_matches=template_matches,
            enriched_files=enriched_files,
        )

        return causal_graph, impact_tree, template_matches, system_deltas, directly_changed, structured_hypotheses

    def _build_structured_hypotheses(
        self,
        causal_graph: Any,
        impact_tree: Any,
        risk_patterns: list,
        template_matches: list[dict],
        enriched_files: list[dict],
    ) -> list[dict]:
        """
        Build structured hypotheses attached to causal edges.
        Replaces the old 'unknowns = dump zone for inference' pattern.
        
        Each hypothesis is a testable claim about what might go wrong,
        attached to a specific causal edge in the graph.
        """
        hypotheses: list[dict] = []

        # Get impacted symbols from propagation
        impacted = impact_tree.get_impacted_symbols(min_confidence=0.15) if impact_tree else []

        # For each impacted symbol with an incoming causal edge, build a hypothesis
        for symbol in impacted[:15]:  # cap at 15
            if not impact_tree:
                continue
            node = impact_tree.all_nodes.get(symbol)
            if not node or not node.incoming_edges:
                continue

            for edge in node.incoming_edges:
                # Compute hypothesis confidence from edge + propagation
                hypothesis_confidence = edge.confidence * node.confidence * 0.9

                # Generate hypothesis based on edge type
                if edge.edge_type == "data_flow":
                    template = "If {from_symbol} changes, {to_symbol} may receive unexpected input through data flow"
                elif edge.edge_type == "control_flow":
                    template = "If {from_symbol} changes, {to_symbol} execution gating may be altered"
                elif edge.edge_type == "shared_state":
                    template = "If {from_symbol} changes, {to_symbol} may read inconsistent shared state"
                elif edge.edge_type == "async_event":
                    template = "If {from_symbol} changes, event emitted to {to_symbol} may carry unexpected payload"
                elif edge.edge_type == "db_dependency":
                    template = "If {from_symbol} changes, {to_symbol} may read stale or inconsistent DB state"
                elif edge.edge_type == "transaction_boundary":
                    template = "If {from_symbol} fails, {to_symbol} may roll back due to shared transaction boundary"
                else:
                    continue

                hypothesis = {
                    "from_symbol": edge.from_symbol,
                    "to_symbol": edge.to_symbol,
                    "edge_type": edge.edge_type,
                    "hypothesis": template.format(from_symbol=edge.from_symbol, to_symbol=edge.to_symbol),
                    "confidence": round(hypothesis_confidence, 3),
                    "propagation_path": [edge.from_symbol, edge.to_symbol],
                    "source": "causal_propagation",
                }

                # Cross-reference with failure template matches
                for tmpl in template_matches:
                    tmpl_name = tmpl.get("template_name", "")
                    tmpl_regions = tmpl.get("matched_system_regions", [])
                    if any(r.lower() in symbol.lower() or symbol.lower() in r.lower() for r in tmpl_regions):
                        hypothesis["related_failure_template"] = tmpl_name
                        hypothesis["confidence"] = min(1.0, hypothesis_confidence + 0.15)
                        break

                hypotheses.append(hypothesis)

        # Sort by confidence descending
        hypotheses.sort(key=lambda h: -h["confidence"])
        return hypotheses[:20]

    def _run_llm_with_causal_context(
        self,
        compressed_for_llm: dict[str, Any],
        causal_graph: Any,
        impact_tree: Any,
        template_matches: list[dict[str, Any]],
        system_deltas: list[SystemBehaviorDelta],
        risk_patterns: list | None = None,
        structured_hypotheses: list[dict] | None = None,
    ) -> dict:
        """Call LLM with causal context and score scenarios."""
        output = self.failure_simulation_llm.generate(
            compressed_ir=compressed_for_llm,
            causal_graph=causal_graph.to_dict(),
            impact_tree=impact_tree.get_blast_radius(),
            failure_template_matches=template_matches,
            system_behavior_deltas=[d.to_dict() for d in system_deltas],
        )
        failure_simulation = output.model_dump()

        # Sanitize LLM output
        failure_simulation = self._sanitize_llm_output(failure_simulation)

        # Add causal artifacts
        if not failure_simulation.get("system_behavior_deltas"):
            failure_simulation["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
        if not failure_simulation.get("matched_failure_templates"):
            failure_simulation["matched_failure_templates"] = template_matches
        if not failure_simulation.get("blast_radius"):
            failure_simulation["blast_radius"] = impact_tree.get_blast_radius()

        # Attach structured hypotheses (replaces unknowns dump zone)
        if structured_hypotheses and not failure_simulation.get("structured_hypotheses"):
            failure_simulation["structured_hypotheses"] = structured_hypotheses

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

        # Aggregate verdict (thread risk_patterns explicitly — fixes bug with self.risk_patterns)
        failure_simulation = self._aggregate_verdict(
            failure_simulation=failure_simulation,
            validation_score=validation_score,
            impact_tree=impact_tree,
            risk_patterns=risk_patterns,
        )

        return failure_simulation


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
        # Collect (file_path, content) pairs for repo-wide symbol indexing.
        # We already fetch these snapshots for the diff, so we reuse them
        # to build a partial-but-real repo index — no extra HTTP calls.
        # The index expands `known_symbols` in the causal graph and unlocks
        # richer blast radius propagation. (Task H — repo-wide symbol index.)
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
            # Track this snapshot for repo-wide index construction.
            repo_index_files.append((file["file_path"], snapshot.content))

        # Build the repo-wide symbol index from the snapshots we already have.
        # This is the smallest correct change: reuses already-fetched data,
        # adds zero new HTTP calls, and unlocks propagation to reach past
        # the diff boundary into unchanged helper functions.
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
        legacy_compressed = compressor.compress(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected,
        )
        compressed_for_llm = compressor.compress_v3(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected, behavior_diffs=behavior_diffs,
        )

        # ==========================================================
        # PIPELINE: Causal graph -> propagation -> templates -> LLM -> scenarios -> verdict
        # ==========================================================
        # `repo_index` is the Task H repo-wide symbol index. It may be None
        # if no snapshots were available (e.g. all files were excluded) —
        # the pipeline handles that gracefully and falls back to diff-only.
        causal_graph, impact_tree, template_matches, system_deltas, directly_changed, structured_hypotheses = self._run_causal_pipeline(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            behavior_diffs=behavior_diffs, compressed_for_llm=compressed_for_llm,
            repo_index=repo_index,
        )

        try:
            if self.failure_simulation_llm:
                print("Calling LLM with causal graph, impact tree, and failure templates...")
                failure_simulation = self._run_llm_with_causal_context(
                    compressed_for_llm=compressed_for_llm,
                    causal_graph=causal_graph,
                    impact_tree=impact_tree,
                    template_matches=template_matches,
                    system_deltas=system_deltas,
                    risk_patterns=risk_patterns,
                    structured_hypotheses=structured_hypotheses,
                )
            else:
                failure_simulation = self._default_failure_simulation()
                failure_scenario_lines = FailureSimulator().generate(risk_patterns, enriched_files)
                failure_simulation["failure_scenarios"] = [
                    {"title": line, "evidence_type": "inferred", "silent_failure": True, "merge_risk_level": "MEDIUM", "hop_confidence": 1.0}
                    for line in failure_scenario_lines
                ]
                failure_simulation["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
                failure_simulation["matched_failure_templates"] = template_matches
                failure_simulation["blast_radius"] = impact_tree.get_blast_radius()
                failure_simulation["causal_graph"] = causal_graph.to_dict()
                failure_simulation["structured_hypotheses"] = structured_hypotheses

        except Exception as e:
            print(f"LLM failure simulation failed, falling back to rules: {repr(e)}")
            failure_simulation = self._default_failure_simulation()
            failure_scenario_lines = FailureSimulator().generate(risk_patterns, enriched_files)
            failure_simulation["failure_scenarios"] = [
                {"title": line, "evidence_type": "inferred", "silent_failure": True, "merge_risk_level": "MEDIUM", "hop_confidence": 1.0}
                for line in failure_scenario_lines
            ]
            failure_simulation["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
            failure_simulation["matched_failure_templates"] = template_matches
            failure_simulation["blast_radius"] = impact_tree.get_blast_radius()
            failure_simulation["structured_hypotheses"] = structured_hypotheses
            failure_simulation["causal_graph"] = causal_graph.to_dict()

        data = self._build_result(
            repo=request.repo, pr_number=request.pr_number,
            analysis_mode=AnalysisMode.FULL_FILE,
            failure_simulation=failure_simulation,
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected, system_impact=system_impact,
            excluded_files=excluded_files, compressed_for_llm=compressed_for_llm,
        )

        # Add analysis artifacts
        data["behavior_deltas"] = [d.__dict__ for d in behavior_deltas]
        data["behavior_diffs"] = [{"symbol": d.symbol, "before": d.before, "after": d.after} for d in behavior_diffs]
        data["legacy_compressed_ir"] = legacy_compressed
        data["reachability"] = {k: v.__dict__ for k, v in reachability_results.items()}
        data["side_effects"] = {k: v.__dict__ for k, v in side_effect_results.items()}
        data["causal_graph"] = causal_graph.to_dict()
        data["impact_tree"] = impact_tree.get_blast_radius()
        data["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
        data["matched_failure_templates"] = template_matches
        data["structured_hypotheses"] = structured_hypotheses

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
        legacy_compressed = compressor.compress(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected,
        )
        compressed_for_llm = compressor.compress_v3(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected, behavior_diffs=behavior_diffs,
        )

        # ==========================================================
        # PIPELINE: Causal graph -> propagation -> templates -> scenarios -> verdict
        # ==========================================================
        causal_graph, impact_tree, template_matches, system_deltas, directly_changed, structured_hypotheses = self._run_causal_pipeline(
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            behavior_diffs=behavior_diffs, compressed_for_llm=compressed_for_llm,
        )

        try:
            if self.failure_simulation_llm:
                print("Calling LLM with causal graph, impact tree, and failure templates...")
                failure_simulation = self._run_llm_with_causal_context(
                    compressed_for_llm=compressed_for_llm,
                    causal_graph=causal_graph,
                    impact_tree=impact_tree,
                    template_matches=template_matches,
                    system_deltas=system_deltas,
                    risk_patterns=risk_patterns,
                    structured_hypotheses=structured_hypotheses,
                )
            else:
                failure_simulation = self._default_failure_simulation()
                failure_scenario_lines = FailureSimulator().generate(risk_patterns, enriched_files)
                failure_simulation["failure_scenarios"] = [
                    {"title": line, "evidence_type": "inferred", "silent_failure": True, "merge_risk_level": "MEDIUM", "hop_confidence": 1.0}
                    for line in failure_scenario_lines
                ]
                failure_simulation["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
                failure_simulation["matched_failure_templates"] = template_matches
                failure_simulation["blast_radius"] = impact_tree.get_blast_radius()
                failure_simulation["causal_graph"] = causal_graph.to_dict()
                failure_simulation["structured_hypotheses"] = structured_hypotheses

        except Exception as e:
            print(f"LLM failure simulation failed, falling back to rules: {repr(e)}")
            failure_simulation = self._default_failure_simulation()
            failure_scenario_lines = FailureSimulator().generate(risk_patterns, enriched_files)
            failure_simulation["failure_scenarios"] = [
                {"title": line, "evidence_type": "inferred", "silent_failure": True, "merge_risk_level": "MEDIUM", "hop_confidence": 1.0}
                for line in failure_scenario_lines
            ]
            failure_simulation["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
            failure_simulation["matched_failure_templates"] = template_matches
            failure_simulation["blast_radius"] = impact_tree.get_blast_radius()
            failure_simulation["structured_hypotheses"] = structured_hypotheses

        data = self._build_result(
            repo=request.get("repo", "example/repo"),
            pr_number=request.get("pr_number", 1),
            analysis_mode=AnalysisMode.DIFF_ONLY,
            failure_simulation=failure_simulation,
            enriched_files=enriched_files, risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected, system_impact=system_impact,
            excluded_files=excluded_files, compressed_for_llm=compressed_for_llm,
        )

        # Add analysis artifacts
        data["behavior_deltas"] = [d.__dict__ for d in behavior_deltas]
        data["behavior_diffs"] = [{"symbol": d.symbol, "before": d.before, "after": d.after} for d in behavior_diffs]
        data["legacy_compressed_ir"] = legacy_compressed
        data["reachability"] = {k: v.__dict__ for k, v in reachability_results.items()}
        data["side_effects"] = {k: v.__dict__ for k, v in side_effect_results.items()}
        data["causal_graph"] = causal_graph.to_dict()
        data["impact_tree"] = impact_tree.get_blast_radius()
        data["system_behavior_deltas"] = [d.to_dict() for d in system_deltas]
        data["matched_failure_templates"] = template_matches
        data["structured_hypotheses"] = structured_hypotheses

        return data

    def publish_comments(self, result: dict[str, Any]) -> dict[str, Any]:
        comment = self._render_pr_comment("github/pr_comment.md.j2", result)
        result["generated_comment"] = comment
        print(comment)
        return result

    async def log_run(self, result: dict[str, Any]) -> None:
        await persist_analysis_result(result)
        print(f"Logged analysis run for {result.get('repo', 'example/repo')} PR #{result.get('pr_number', 1)}")