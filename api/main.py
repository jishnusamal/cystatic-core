from __future__ import annotations

from fastapi import FastAPI

from api.schemas import AnalyzeRequest, BlastRadiusResponse, HealthResponse
from core_engine.dependency_graph import DependencyGraph
from core_engine.refactor_risk import RefactorRiskEstimator

app = FastAPI(title="Cystatic", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/v1/blast-radius", response_model=BlastRadiusResponse)
def blast_radius(body: AnalyzeRequest) -> BlastRadiusResponse:
    """
    Placeholder: builds a tiny graph from ``changed_paths`` and returns risk for the first path.
    """
    g = DependencyGraph()
    primary = body.changed_paths[0] if body.changed_paths else "."
    for p in body.changed_paths[1:]:
        g.add_edge(p, primary)
    est = RefactorRiskEstimator(g)
    r = est.estimate(primary)
    # blast_radius returns dependents; expose as affected "files"
    affected = sorted(g.blast_radius(primary))
    return BlastRadiusResponse(
        affected_files=affected,
        impact_score=r.impact_score,
        risk_level=r.risk_level,
    )
