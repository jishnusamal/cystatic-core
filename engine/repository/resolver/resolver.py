from typing import Sequence
import asyncio
from core.logging import pipeline_logger
from engine.repository.store import RepositoryStore
from engine.repository.materialization.materializer import RepositoryMaterializer
from engine.repository.materialization.request import MaterializationRequest
from integrations.base import RepositoryProvider
from .requirements import ResolutionRequirement, SymbolResolutionRequirement
from .frontier import ResolutionFrontier
from .planner import RequirementPlanner, DefaultRequirementPlanner
from typing import Any

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
        planner: RequirementPlanner | None = None,
        tree_metadata: Any = None,
        base_commit: str | None = None,
        budget: Any = None,
    ) -> None:
        self.store = store
        self.source = source
        self.materializer = materializer
        self.planner = planner or DefaultRequirementPlanner(store, source)
        self.tree_metadata = tree_metadata
        self.base_commit = base_commit
        self.budget = budget

    async def resolve(
        self,
        repository_id: str,
        commit_sha: str,
        requirements: Sequence[ResolutionRequirement],
    ) -> None:
        """
        Asynchronously resolve a set of requirements, materializing necessary files.
        """
        # Initialize frontier with the incoming requirements
        frontier = ResolutionFrontier()
        for req in requirements:
            frontier.unresolved.add(req)
            if isinstance(req, SymbolResolutionRequirement):
                frontier.add_symbol(req.symbol_id)

        pipeline_logger.log_pipeline(
            f"[Resolver] Starting frontier resolution with {len(requirements)} requirements for {repository_id}@{commit_sha}",
            to_terminal=True,
        )

        round_num = 0
        while frontier.has_work():
            round_num += 1
            # Current batch of unresolved requirements
            current_reqs = list(frontier.unresolved)
            pipeline_logger.log_pipeline(
                f"[Resolver][Round {round_num}] Planning {len(current_reqs)} requirements",
                to_terminal=True,
            )

            # Planner returns MaterializationRequest objects for all requirements
            candidate_requests = await self.planner.plan(
                repository_id, commit_sha, current_reqs
            )
            # Aggregate all paths that still need materialization
            missing_paths = set()
            for req in candidate_requests:
                for p in req.paths:
                    if not self.store.is_materialized(repository_id, commit_sha, p):
                        missing_paths.add(p)

            pipeline_logger.log_pipeline(
                f"[Resolver][Round {round_num}] {len(candidate_requests)} candidate requests, {len(missing_paths)} missing",
                to_terminal=True,
            )

            if missing_paths:
                request = MaterializationRequest(
                    repository_id=repository_id,
                    commit_sha=commit_sha,
                    paths=tuple(sorted(list(missing_paths))),
                    reason="resolution_frontier",
                )
                await self.materializer.materialize(request)

            # After materialization, assume current requirements are satisfied.
            # In a full implementation we would re‑query for newly uncovered requirements.
            frontier.unresolved.clear()
            frontier.symbols.clear()

        pipeline_logger.log_pipeline(
            f"[Resolver] Frontier resolution complete after {round_num} rounds",
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
