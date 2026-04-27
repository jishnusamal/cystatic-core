from __future__ import annotations
from fastapi import FastAPI, APIRouter, Depends, Body, Header, Request, Response, status
from tortoise.contrib.fastapi import register_tortoise

# Internal imports
from schemas import AnalyzeRequest
from api.utils import verify_api_key
from api.settings import get_settings
from source_adapters import GitHubSource, GitHubPublisher
from language_adapters import PythonAdapter
from core_engine.orchestrator import Orchestrator, DiffOrchestrator
from core_engine.failure_simulation_llm import FailureSimulationLLM
from api.db import TORTOISE_ORM
from instrumentation import sentry, sentry_pr_context

settings = get_settings()
app = FastAPI(title="Cystatic", version=settings.app_version)
sentry.attach_middleware(app) 
router = APIRouter(prefix="/v1")


def build_failure_simulation_llm() -> FailureSimulationLLM | None:
    api_key = settings.llm_api_key or settings.ai_api_key
    
    print("LLM api key exists:", bool(api_key))
    print("LLM model:", settings.llm_model)
    print("LLM base url:", settings.llm_base_url)

    if not api_key:
        return None

    return FailureSimulationLLM(
        api_key=api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        site_url=settings.llm_base_url,
        site_name=settings.llm_base_url,
    )

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
async def analyze_pr(body: AnalyzeRequest = Body(...)):
    failure_simulation_llm = build_failure_simulation_llm()
    orchestrator = Orchestrator(
        request=body,
        source=GitHubSource(token=settings.github_access_token),
        language=PythonAdapter(),
        publisher=GitHubPublisher(token=settings.github_access_token),
        failure_simulation_llm=failure_simulation_llm,
    )
    result = orchestrator.run_pr_analysis()
    orchestrator.publish_comments(result)

    if settings.app_env == "production":
        await orchestrator.log_run(result)
    return result

@router.post("/analyze-diff")
async def analyze_diff(body: str = Body(..., media_type="text/plain")):
    diff_text = body
    # print(f"Received diff for analysis:\n{diff_text[:500]}...")  # Log the first 500 chars of the diff

    failure_simulation_llm = build_failure_simulation_llm()
    orchestrator = DiffOrchestrator(
        request={
            "diff": diff_text
        },  
        source=GitHubSource(token=settings.github_access_token),  # if needed for parsing
        language=PythonAdapter(),
        failure_simulation_llm=failure_simulation_llm,
    )

    result = orchestrator.run_pr_analysis()

    if settings.app_env == "production":
        await orchestrator.log_run(result)
    
    return orchestrator.publish_comments(result)

app.include_router(router)

register_tortoise(
    app,
    config=TORTOISE_ORM,
    generate_schemas=False,
    add_exception_handlers=True,
)