from schemas import AnalyzeRequest
from jinja2 import Environment, FileSystemLoader
from api.models import AnalysisRecord

class BaseOrchestrator:
    def __init__(self, request, source, language, publisher=None):
        self.request = request
        self.source = source
        self.language = language
        self.publisher = publisher
    
    def run_pr_analysis(self):
        raise NotImplementedError("Must implement run_pr_analysis in subclass")
    
    def publish_comments(self, result: dict):
        raise NotImplementedError("Must implement publish_comments in subclass")
    
    def log_run(self, result: dict):
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
        
    def _get_verdict(self, pr_risk_level: str) -> str:
        if "HIGH" in pr_risk_level:
            return "BLOCK_REVIEW"
        elif "MEDIUM" in pr_risk_level:
            return "REVIEW_REQUIRED"
        else:
            return "SAFE_TO_MERGE"
        
    def _render_pr_comment(self, template: str, result: dict) -> str:
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template(template)
        
        def risk_priority(risk_level: str) -> int:
            if "HIGH" in risk_level:
                return 3
            elif "MEDIUM" in risk_level:
                return 2
            return 1

        files = result.get("files", [])

        # sort: HIGH → MEDIUM → LOW, then by score
        files = sorted(
            files,
            key=lambda f: (risk_priority(f["risk_level"]), f["risk_score"]),
            reverse=True
        )

        # filter out LOW risk files
        files = [f for f in files]
        #  files = [f for f in files if "LOW" not in f["risk_level"]]

        return template.render(
            pr_risk_score=result.get("pr_risk_score", 0),
            pr_risk_level=result.get("pr_risk_level", "UNKNOWN"),
            verdict=result.get("verdict", "UNKNOWN"),
            files=files
        )

class Orchestrator(BaseOrchestrator):
    def __init__(self, request: AnalyzeRequest, source, language, publisher):
        super().__init__(request, source, language, publisher)
    
    def run_pr_analysis(self):
        (request, source, lang) = (self.request, self.source, self.language)
        
        diff = source.fetch_diff(request.repo, request.pr_number)
        sha = source.get_head_sha(request.repo, request.pr_number)

        files = lang.extract_changed_files(diff) or []

        enriched_files = []

        for file in files:
            print(f"Processing file: {file['file_path']}")

            snapshot = source.fetch_file_at_sha(
                repo=request.repo,
                file_path=file["file_path"],
                sha=sha
            )

            # 1. changed functions
            changed_functions = lang.extract_changed_functions(
                file=file,
                content=snapshot.content
            )

            # 2. endpoints (FastAPI only)
            endpoints = lang.extract_endpoints_if_fastapi(
                file_path=file["file_path"],
                content=snapshot.content
            )

            # 3. filter endpoints impacted by changed functions
            impacted_endpoints = [
                ep for ep in endpoints
                if ep["function"] in changed_functions
            ]

            enriched_file = {
                "file_path": file["file_path"],
                "lines_changed": file["lines_changed"],
                "total_functions_changed": len(changed_functions),
                "total_endpoints": len(impacted_endpoints),
                "changed_functions": changed_functions,
                "endpoints": impacted_endpoints
            }
            
            enriched_file["risk_score"] = self._calculate_file_risk_score(enriched_file)
            enriched_file["risk_level"] = self._classify_risk(enriched_file["risk_score"])
            enriched_files.append(enriched_file)
            
        pr_risk_score = self._calculate_pr_risk_score(enriched_files)
        pr_risk_level = self._classify_risk(pr_risk_score)

        result = {
            "repo": request.repo,
            "pr_number": request.pr_number,
            "files": enriched_files,
            "pr_risk_score": pr_risk_score,
            "pr_risk_level": pr_risk_level,
            "verdict": self._get_verdict(pr_risk_level)
        }

        return result
    
    def publish_comments(self, result: dict):
        publisher, request = self.publisher, self.request
        
        comment = self._render_pr_comment("github/pr_comment_1.md.j2", result)
        
        print(f"Publishing comment to {request.repo} PR #{request.pr_number}:\n{comment}")

        # publisher.post_comment(
        #     repo=request.repo,
        #     pr_number=request.pr_number,
        #     comment=comment
        # )
        
    async def log_run(self, result: dict):
        record = await AnalysisRecord.create(
            repo=self.request.repo,
            pr_number=self.request.pr_number,
            analysis_result=result
        )
        print(f"Logged analysis record with ID: {record}")
        
        
class DiffOrchestrator(BaseOrchestrator):
    def __init__(self, request, source, language):
        super().__init__(request, source, language)
        self.language = language
        self.request = request
        self.source = source

    
    def run_pr_analysis(self):
        (request, source, lang) = (self.request, self.source, self.language)
        
        diff = request.get("diff") or ""
        diff = source._format_diff(diff)

        files = lang.extract_changed_files(diff) or []

        enriched_files = []

        for file in files:
            enriched_file = {
                "file_path": file["file_path"],
                "lines_changed": file["lines_changed"],
            }
            
            enriched_file["risk_score"] = self._calculate_file_risk_score(enriched_file)
            enriched_file["risk_level"] = self._classify_risk(enriched_file["risk_score"])
            enriched_files.append(enriched_file)
            
        pr_risk_score = self._calculate_pr_risk_score(enriched_files)
        pr_risk_level = self._classify_risk(pr_risk_score)

        result = {
            "repo": "example/repo", # dummy
            "pr_number": 1, # dummy
            "files": enriched_files,
            "pr_risk_score": pr_risk_score,
            "pr_risk_level": pr_risk_level,
            "verdict": self._get_verdict(pr_risk_level)
        }

        return result
    
    def publish_comments(self, result: dict):
        request =  self.request
        

        comment = self._render_pr_comment("github/pr_comment.md.j2", result)
        # comment = self._render_pr_comment(result)
        return f"Publishing comment to {result['repo']} PR #{result['pr_number']}:\n{comment}"