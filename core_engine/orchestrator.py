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

            enriched_files.append({
                "file_path": file["file_path"],
                "lines_changed": file["lines_changed"],
                "changed_functions": changed_functions,
                "endpoints": impacted_endpoints
            })

        result = {
            "repo": request.repo,
            "pr_number": request.pr_number,
            "files": enriched_files,
        }

        return result
    
    def publish_comments(self, analysis_result):
        publisher, request = self.publisher, self.request
        
        publisher.post_comment(
            repo=request.repo,
            pr_number=request.pr_number,
            comment=f"Analyzed PR #{request.pr_number}"
        )