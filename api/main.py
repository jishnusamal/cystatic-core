from __future__ import annotations
from fastapi import FastAPI, APIRouter, Depends, Body, Request, Response, status
from .schemas import AnalyzeRequest, BlastRadiusResponse, HealthResponse
from .utils import verify_api_key
from .settings import get_settings
from source_adapters import GitHubSource, GitHubPublisher
from utils.unzip import extract_zip

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
# def analyze_pr(body: AnalyzeRequest) -> AnalyzeRequest:
def analyze_pr(body: AnalyzeRequest = Body(...)):
    print(body)
    # comment = f"Analyzed PR #{body.pr_number} with diff URL {body.diff_url}."
    # github_publisher = GitHubPublisher(token=settings.github_access_token)
    # github_publisher.post_comment(
    #     repo=body.repo,
    #     pr_number=body.pr_number,
    #     comment=comment
    # )
    return body

app.include_router(router)