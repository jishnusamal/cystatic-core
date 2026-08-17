from typing import Sequence
import asyncio
from core.logging import pipeline_logger
from engine.repository.store import RepositoryStore
from engine.repository.materialization.materializer import RepositoryMaterializer
from engine.repository.materialization.request import MaterializationRequest
from integrations.base import RepositoryProvider
from .requirements import ResolutionRequirement
from .frontier import ResolutionFrontier
from .planner import RequirementPlanner

class RepositoryResolver:
    """
    Coordinates lazy-resolution: plans requirements, creates materialization requests,
    invokes the materializer, and updates the repository store.
    """

    def __init__(
        self,
        store: RepositoryStore,
        source: RepositoryProvider,
        materializer: RepositoryMaterializer,
    ) -> None:
        self.store = store
        self.source = source
        self.materializer = materializer
        self.planner = RequirementPlanner(store, source)

    async def resolve(
        self,
        repository_id: str,
        commit_sha: str,
        requirements: Sequence[ResolutionRequirement],
    ) -> None:
        """
        Asynchronously resolve a set of requirements, materializing necessary files.
        """
        frontier = ResolutionFrontier()
        for req in requirements:
            frontier.add(req)

        pipeline_logger.log_pipeline(
            f"[Resolver] Resolving {len(requirements)} requirements for {repository_id}@{commit_sha}",
            to_terminal=True,
        )

        while not frontier.is_empty():
            current_reqs = []
            while not frontier.is_empty():
                req = frontier.pop()
                if req:
                    current_reqs.append(req)

            if not current_reqs:
                break

            paths_to_materialize = await self.planner.plan(
                repository_id, commit_sha, current_reqs
            )

            if not paths_to_materialize:
                continue

            request = MaterializationRequest(
                repository_id=repository_id,
                commit_sha=commit_sha,
                paths=tuple(sorted(list(paths_to_materialize))),
                reason="resolver_lazy_resolution",
            )

            pipeline_logger.log_pipeline(
                f"[Resolver] Materializing {len(paths_to_materialize)} files...",
                to_terminal=True,
            )

            result = await self.materializer.materialize(request)

            pipeline_logger.log_pipeline(
                f"[Resolver] Materialized {len(result.materialized_paths)} files, "
                f"already materialized: {len(result.already_materialized_paths)}, "
                f"failed: {len(result.failed_paths)}",
                to_terminal=True,
            )

    def resolve_sync(
        self,
        repository_id: str,
        commit_sha: str,
        requirements: Sequence[ResolutionRequirement],
    ) -> None:
        """
        Synchronously resolve requirements. Runs the async resolve method.
        Safe to call from a running event loop (runs in a helper thread).
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        coro = self.resolve(repository_id, commit_sha, requirements)

        if loop and loop.is_running():
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, coro)
                future.result()
        else:
            asyncio.run(coro)
