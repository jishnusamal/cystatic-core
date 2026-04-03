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


# @router.get("/health", )
# def health() -> HealthResponse:
#     return HealthResponse()

@app.api_route(
    "/health",
    methods=["GET", "HEAD"],
    dependencies=[Depends(get_settings)],
)
async def health(request: Request):
    if request.method == "HEAD":
        return Response(status_code=status.HTTP_200_OK)
    
    return {"status": "ok"}

# @router.post("/analyze-pr", response_model=BlastRadiusResponse, dependencies=[Depends(verify_api_key)])
# def analyze_pr(body: AnalyzeRequest) -> BlastRadiusResponse:
#     """
#     Placeholder: builds a tiny graph from ``changed_paths`` and returns risk for the first path.
#     """
#     return BlastRadiusResponse(
#         affected_files=[body.changed_paths[0] if body.changed_paths else "."],
#         impact_score=0.5,
#         risk_level="medium",
#     )
    # g = DependencyGraph()
    # primary = body.changed_paths[0] if body.changed_paths else "."
    # for p in body.changed_paths[1:]:
    #     g.add_edge(p, primary)
    # est = RefactorRiskEstimator(g)
    # r = est.estimate(primary)
    # # blast_radius returns dependents; expose as affected "files"
    # affected = sorted(g.blast_radius(primary))
    # return BlastRadiusResponse(
    #     affected_files=affected,
    #     impact_score=r.impact_score,
    #     risk_level=r.risk_level,
    # )

@router.post("/analyze-pr", dependencies=[Depends(verify_api_key)])
# def analyze_pr(body: AnalyzeRequest) -> AnalyzeRequest:
def analyze_pr(body):
    print(body)
    comment = f"Analyzed PR #{body.pr_number} with diff URL {body.diff_url}."
    github_publisher = GitHubPublisher(token=settings.github_access_token)
    github_publisher.post_comment(
        repo=body.repo,
        pr_number=body.pr_number,
        comment=comment
    )
    return body

app.include_router(router)