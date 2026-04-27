from schemas import AnalyzeRequest
from jinja2 import Environment, FileSystemLoader, Template  # pyright: ignore[reportMissingImports]
from api.models import AnalysisRecord
from language_adapters.python.python_adapter import AnalysisMode
from core_engine.risk_pattern_detector import RiskPatternDetector, detect_flows
from core_engine.failure_simulator import FailureSimulator
from core_engine.entrypoint_resolver import EntryPointResolver
from core_engine.file_exclusion import FileExclusionService
from core_engine.rir_compressor import RIRCompressor
from typing import Any
import json


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
    
    #---------------------------------------------
    # Risk Scoring Logic (Private methods)
    #---------------------------------------------
    def _calculate_file_risk_score(self, file_data: dict) -> float:
        """
        Returns risk score as percentage (0-100)
        """

        lines_changed = file_data.get("lines_changed", 0)
        functions_changed = file_data.get("total_functions_changed", 0)
        num_endpoints = file_data.get("total_endpoints", 0)

        MAX_LINES = 20
        MAX_FUNCTIONS = 5

        normalized_lines = min(lines_changed / MAX_LINES, 1.0)
        normalized_functions = min(functions_changed / MAX_FUNCTIONS, 1.0)

        # base score (0–1)
        risk_score = (
            normalized_lines * 0.5 +
            normalized_functions * 0.3
        )

        # amplification
        risk_score *= (1 + 0.2 * num_endpoints)

        # clamp to 1.0
        risk_score = min(risk_score, 1.0)

        # convert to percentage
        return round(risk_score * 100, 2)
    
    def _calculate_pr_risk_score(self, files: list[dict]) -> float:
        if not files:
            return 0.0

        scores = [file["risk_score"] for file in files]

        max_score = max(scores)
        avg_score = sum(scores) / len(scores)

        # weighted blend
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

        failure_simulation = result.get("failure_simulation") or {}

        # Normalize shape to avoid Jinja crashes
        failure_simulation.setdefault("failure_scenarios", [])
        failure_simulation.setdefault("hidden_impact_chain", [])
        failure_simulation.setdefault("missing_critical_tests", [])
        failure_simulation.setdefault("broken_assumptions", [])
        failure_simulation.setdefault("final_question", None)

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
        pr_risk_score = self._calculate_pr_risk_score(enriched_files)
        pr_risk_level = self._classify_risk(pr_risk_score)

        keywords_detected = [
            signal
            for file in enriched_files
            for signal in file.get("keyword_signals", [])
        ]

        allowed_llm_verdicts = {"SAFE", "REVIEW_REQUIRED", "BLOCK_REVIEW"}

        llm_verdict = None
        if isinstance(failure_simulation, dict):
            llm_verdict = failure_simulation.get("verdict")

        final_verdict = (
            llm_verdict
            if llm_verdict in allowed_llm_verdicts
            else self._get_verdict(pr_risk_level, risk_patterns=risk_patterns)
        )

        return {
            "repo": repo,
            "pr_number": pr_number,
            "analysis_mode": analysis_mode.value,
            # "files": enriched_files,
            # "excluded_files": excluded_files or [],
            # "keywords_detected": keywords_detected,
            # "risk_patterns": [
            #     rp.model_dump() if hasattr(rp, "model_dump") else rp
            #     for rp in (risk_patterns or [])
            # ],
            "failure_simulation": failure_simulation or [],
            # "entry_points_affected": [
            #     ep.model_dump() if hasattr(ep, "model_dump") else ep
            #     for ep in (entry_points_affected or [])
            # ],
            # "compressed_for_llm": compressed_for_llm or {},
            # "system_impact": [
            #     impact.model_dump() if hasattr(impact, "model_dump") else impact
            #     for impact in (system_impact or [])
            # ],
            # "pr_risk_score": pr_risk_score,
            # "pr_risk_level": pr_risk_level,
            "verdict": final_verdict,
        }

    def _validate_failure_simulation(
        self,
        failure_simulation: dict,
        compressed_for_llm: dict,
    ) -> dict:
        """
        Ensures LLM output is grounded in real PR data.
        Drops hallucinated scenarios.
        """

        if not isinstance(failure_simulation, dict):
            return {}

        ir_text = json.dumps(compressed_for_llm).lower()

        valid_scenarios = []

        for scenario in failure_simulation.get("failure_scenarios", []):
            combined_text = " ".join([
                scenario.get("title", ""),
                scenario.get("trigger", ""),
                scenario.get("execution_path", ""),
                scenario.get("production_impact", ""),
            ]).lower()

            # Require at least one meaningful token to exist in IR
            tokens = [t for t in combined_text.split() if len(t) > 6]

            if any(token in ir_text for token in tokens):
                valid_scenarios.append(scenario)

        # overwrite with validated scenarios
        failure_simulation["failure_scenarios"] = valid_scenarios

        # If everything got filtered → downgrade
        if not valid_scenarios:
            failure_simulation["verdict"] = "REVIEW_REQUIRED"
            failure_simulation["final_question"] = (
                "No grounded failure scenario could be validated against the PR analysis input."
            )

        return failure_simulation



class Orchestrator(BaseOrchestrator):
    """
    Repo-aware orchestrator.

    Uses:
    - GitHub PR diff
    - PR head SHA
    - full file snapshots
    - AST-based function mapping
    """

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
                excluded_files.append(
                    {
                        "file_path": file_path,
                        "reason": f"matched {matched}",
                    }
                )
                continue
            kept_files.append(file)
        diff_ir.files = kept_files

        sha = source.get_head_sha(request.repo, request.pr_number)

        files = lang.extract_changed_files(diff_ir) or []
        enriched_files = []

        for file in files:
            print(f"Processing file in FULL_FILE mode: {file['file_path']}")

            snapshot = source.fetch_file_at_sha(
                repo=request.repo,
                file_path=file["file_path"],
                sha=sha,
            )

            changed_functions = lang.extract_changed_functions(
                file=file,
                mode=AnalysisMode.FULL_FILE,
                content=snapshot.content,
            )
            keyword_signals = lang.extract_keyword_signals_from_diff(file=file)

            endpoints = lang.extract_endpoints(
                file_path=file["file_path"],
                content=snapshot.content,
            )

            changed_function_names = {fn.name for fn in changed_functions}

            impacted_endpoints = [
                ep for ep in endpoints
                if ep["function"] in changed_function_names
            ]

            enriched_files.append(
                self._enrich_file(
                    file=file,
                    changed_functions=changed_functions,
                    endpoints=impacted_endpoints,
                    keyword_signals=keyword_signals,
                )
            )

        risk_detector = RiskPatternDetector()
        risk_patterns = risk_detector.detect(enriched_files)
        resolver = EntryPointResolver()
        entry_points_affected = resolver.resolve(enriched_files, risk_patterns)
        system_impact = resolver.resolve_system_impact(risk_patterns, entry_points_affected)
        compressed_for_llm = RIRCompressor().compress(
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected,
        )
            
        try:
            if self.failure_simulation_llm:
                print("Calling LLM...")
                output = self.failure_simulation_llm.generate(compressed_for_llm)
                failure_simulation = output.model_dump()

                failure_simulation = self._validate_failure_simulation(
                    failure_simulation=failure_simulation,
                    compressed_for_llm=compressed_for_llm,
                )

            else:
                failure_simulation = FailureSimulator().generate(risk_patterns, enriched_files)

        except Exception as e:
            print(f"LLM failure simulation failed, falling back to rules: {repr(e)}")
            failure_simulation = FailureSimulator().generate(risk_patterns, enriched_files)

        data = self._build_result(
            repo=request.repo,
            pr_number=request.pr_number,
            analysis_mode=AnalysisMode.FULL_FILE,
            failure_simulation=failure_simulation,
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected,
            system_impact=system_impact,
            excluded_files=excluded_files,
            compressed_for_llm=compressed_for_llm,
        )
        
        return data

    def publish_comments(self, result: dict[str, Any]) -> None:
        comment = self._render_pr_comment("github/pr_comment.md.j2", result)
        # pass
        print(
            f"Publishing comment to {self.request.repo} "
            f"PR #{self.request.pr_number}:\n{comment}"
        )

        # self.publisher.post_comment(
        #     repo=self.request.repo,
        #     pr_number=self.request.pr_number,
        #     comment=comment,
        # )

    async def log_run(self, result: dict[str, Any]) -> None:
        record = await AnalysisRecord.create(
            repo=self.request.repo,
            pr_number=self.request.pr_number,
            analysis_result=result,
        )
        print(f"Logged analysis record with ID: {record}")
        
    
class DiffOrchestrator(BaseOrchestrator):
    """
    Demo-safe orchestrator.

    Uses:
    - raw pasted/uploaded diff text
    - no repo access
    - no file fetching
    - regex-based hunk function mapping
    """

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
                excluded_files.append(
                    {
                        "file_path": file_path,
                        "reason": f"matched {matched}",
                    }
                )
                continue
            kept_files.append(file)
        diff_ir.files = kept_files

        files = lang.extract_changed_files(diff_ir) or []
        enriched_files = []

        for file in files:
            print(f"Processing file in DIFF_ONLY mode: {file['file_path']}")

            changed_functions = lang.extract_changed_functions(
                file=file,
                mode=AnalysisMode.DIFF_ONLY,
            )
            keyword_signals = lang.extract_keyword_signals_from_diff(file=file)

            endpoints = lang.extract_endpoints_from_diff_only(file=file)
            changed_function_names = {fn.name for fn in changed_functions}
            impacted_endpoints = [
                ep for ep in endpoints
                if ep["function"] in changed_function_names
            ]

            enriched_files.append(
                self._enrich_file(
                    file=file,
                    changed_functions=changed_functions,
                    endpoints=impacted_endpoints,
                    keyword_signals=keyword_signals,
                )
            )

        risk_detector = RiskPatternDetector()
        risk_patterns = risk_detector.detect(enriched_files)
        resolver = EntryPointResolver()
        entry_points_affected = resolver.resolve(enriched_files, risk_patterns)
        system_impact = resolver.resolve_system_impact(risk_patterns, entry_points_affected)
        compressed_for_llm = RIRCompressor().compress(
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected,
        )
        try:
            if self.failure_simulation_llm:
                print("Calling LLM...")
                output = self.failure_simulation_llm.generate(compressed_for_llm)
                failure_simulation = output.model_dump()

                failure_simulation = self._validate_failure_simulation(
                    failure_simulation=failure_simulation,
                    compressed_for_llm=compressed_for_llm,
                )

            else:
                failure_simulation = FailureSimulator().generate(risk_patterns, enriched_files)

        except Exception as e:
            print(f"LLM failure simulation failed, falling back to rules: {repr(e)}")
            failure_simulation = FailureSimulator().generate(risk_patterns, enriched_files)
            
        data = self._build_result(
            repo=request.get("repo", "example/repo"),
            pr_number=request.get("pr_number", 1),
            analysis_mode=AnalysisMode.FULL_FILE,
            failure_simulation=failure_simulation,
            enriched_files=enriched_files,
            risk_patterns=risk_patterns,
            entry_points_affected=entry_points_affected,
            system_impact=system_impact,
            excluded_files=excluded_files,
            compressed_for_llm=compressed_for_llm,
        )
            
        # print(data)

        return data

    def publish_comments(self, result: dict[str, Any]) -> dict[str, Any]:
        comment = self._render_pr_comment("github/pr_comment.md.j2", result)
        print(comment)
        return result


        # return (
        #     f"Publishing comment to {result['repo']} "
        #     f"PR #{result['pr_number']}:\n{comment}"
        # )

    async def log_run(self, result: dict[str, Any]) -> None:
        record = await AnalysisRecord.create(
            repo=result.get("repo", "example/repo"),
            pr_number=result.get("pr_number", 1),
            analysis_result=result,
        )
        print(f"Logged analysis record with ID: {record.id}")