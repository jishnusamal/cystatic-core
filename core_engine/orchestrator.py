from schemas import AnalyzeRequest

class Orchestrator:
    def __init__(self, request: AnalyzeRequest, source, language, publisher):
        self.source = source
        self.language = language
        self.publisher = publisher
        self.request = request
    
    def run_pr_analysis(self):
        (request, source, lang) = (self.request, self.source, self.language)
        
        diff = source.fetch_diff(request.repo, request.pr_number)
        sha = source.get_head_sha(request.repo, request.pr_number)

        files = lang.extract_changed_files(diff) or []

        enriched_files = []

        for file in files:
            # print(f"Processing file: {file['file_path']}")

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
            enriched_files.append(enriched_file)
            

        result = {
            "repo": request.repo,
            "pr_number": request.pr_number,
            "files": enriched_files,
            "pr_risk_score": self._calculate_pr_risk_score(enriched_files)
            
        }

        return result
    
    def publish_comments(self, result):
        publisher, request = self.publisher, self.request
        
        publisher.post_comment(
            repo=request.repo,
            pr_number=request.pr_number,
            comment=f"Analyzed PR #{request.pr_number}"
        )
        
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