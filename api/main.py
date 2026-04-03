from __future__ import annotations
from fastapi import FastAPI, APIRouter, Depends, Body, Request, Response, status
from .schemas import AnalyzeRequest
from .utils import verify_api_key
from .settings import get_settings
from source_adapters import GitHubSource, GitHubPublisher
from language_adapters import PythonAdapter
from core_engine.orchestrator import run_pr_analysis

app = FastAPI(title="Cystatic", version="0.1.0")
router = APIRouter(prefix="/v1")
settings = get_settings()

@app.api_route(
    "/health",
    methods=["GET", "HEAD"],
    dependencies=[Depends(get_settings)],
)
async def health(request: Request):
    if request.method == "HEAD":
        return Response(status_code=status.HTTP_200_OK)
    
    return {"status": "ok"}


@router.post("/analyze-pr", dependencies=[Depends(verify_api_key)])
def analyze_pr(body: AnalyzeRequest):
    analysis = run_pr_analysis(
        request=body,
        source=GitHubSource(token=settings.github_access_token), 
        lang=PythonAdapter(),
        publisher=GitHubPublisher(token=settings.github_access_token)
    )
    return analysis

app.include_router(router)