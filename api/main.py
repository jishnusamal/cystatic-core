from __future__ import annotations
from fastapi import FastAPI, APIRouter, Depends, Body, Header, Request, Response, status
from schemas import AnalyzeRequest, AnalyzeDiff
from .utils import verify_api_key
from .settings import get_settings
from source_adapters import GitHubSource, GitHubPublisher
from language_adapters import PythonAdapter
from core_engine.orchestrator import Orchestrator, DiffOrchestrator
from instrumentation import sentry, sentry_pr_context


settings = get_settings()
app = FastAPI(title="Cystatic", version=settings.app_version)
sentry.attach_middleware(app) 
router = APIRouter(prefix="/v1")

@app.api_route(
    "/health",
    methods=["GET", "HEAD"],
    dependencies=[Depends(get_settings)],
)
async def health(request: Request):
    if request.method == "HEAD":
        return Response(status_code=status.HTTP_200_OK)
    return {"status": "ok"}

@router.post("/analyze-pr", dependencies=[
        Depends(verify_api_key),
        Depends(sentry_pr_context),
    ])
def analyze_pr(body: AnalyzeRequest = Body(...)):
    orchestrator = Orchestrator(
        request=body,
        source=GitHubSource(token=settings.github_access_token),
        language=PythonAdapter(),
        publisher=GitHubPublisher(token=settings.github_access_token)
    )
    result = orchestrator.run_pr_analysis()
    # print(f"Analysis result for {body.repo} PR #{body.pr_number}: {result}")
    orchestrator.publish_comments(result)
    return result

@router.post("/analyze-diff")
async def analyze_diff(body: str = Body(..., media_type="text/plain")):
    diff_text = body
    # print(f"Received diff for analysis:\n{diff_text[:500]}...")  # Log the first 500 chars of the diff

    orchestrator = DiffOrchestrator(
        request={
            "diff": diff_text
        },  
        source=GitHubSource(token=settings.github_access_token),  # if needed for parsing
        language=PythonAdapter(),
    )

    result = orchestrator.run_pr_analysis()
    
    return orchestrator.publish_comments(result)

app.include_router(router)