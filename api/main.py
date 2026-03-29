from __future__ import annotations
from fastapi import FastAPI, APIRouter, Depends
from .schemas import AnalyzeRequest, BlastRadiusResponse, HealthResponse
from .utils import verify_api_key
from .settings import get_settings
# from core_engine.dependency_graph import DependencyGraph
# from core_engine.refactor_risk import RefactorRiskEstimator



app = FastAPI(title="Cystatic", version="0.1.0")
router = APIRouter(prefix="/v1")



@router.get("/health", response_model=HealthResponse, dependencies=[Depends(get_settings)])
def health() -> HealthResponse:
    return HealthResponse()

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
@router.post("/analyze-pr")
def analyze_pr(body: str) -> str:
    """
    Placeholder: builds a tiny graph from ``changed_paths`` and returns risk for the first path.
    """
    print(body)
    return body

app.include_router(router)