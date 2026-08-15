import pytest
from core.runtime import PREVENT_LEGACY_ARCHITECTURE
from engine.repository.model import RepositoryGraph, RepositoryModel, CallGraph, ReferenceGraph
from engine.language.base.graph_patcher import GraphPatcher
from engine.repository.store import SQLiteRepositoryStore
from engine.repository.store.sink import PersistentFactSink
from engine.repository.facts import File, FileId, Symbol, SymbolId, SymbolKind, Call, CallType
from engine.pipeline.pipeline import Pipeline
from models import RepositoryReference, PullRequestReference, DiffSnapshot, AnalysisRequest, AnalysisTrigger
from models.core import DiffFile, DiffHunk


def test_legacy_architecture_guard_raises():
    """Verify that constructing legacy objects raises RuntimeError when guard is active."""
    token = PREVENT_LEGACY_ARCHITECTURE.set(True)
    try:
        with pytest.raises(RuntimeError, match=r"\[Architecture Assertion\] Attempt to construct 'RepositoryGraph'"):
            RepositoryGraph()

        with pytest.raises(RuntimeError, match=r"\[Architecture Assertion\] Attempt to construct 'RepositoryModel'"):
            RepositoryModel(symbols=frozenset(), call_graph=CallGraph(), reference_graph=ReferenceGraph())

        with pytest.raises(RuntimeError, match=r"\[Architecture Assertion\] Attempt to construct 'GraphPatcher'"):
            GraphPatcher()
    finally:
        PREVENT_LEGACY_ARCHITECTURE.reset(token)


@pytest.mark.asyncio
async def test_production_pipeline_fact_architecture(tmp_path):
    """
    Simulate a production PR analysis:
    - Base facts already in persistent store
    - PR diff with 1 changed file
    - Executes Pipeline.run() with new fact-based architecture
    - Confirms that base_query, repository_view, and change_facts are created
    - Confirms that base_repository_model and head_repository_model remain None
    """
    db_file = str(tmp_path / "test_store.db")
    store = SQLiteRepositoryStore(db_file)
    
    repo_name = "test-org/test-repo"
    base_sha = "sha-base-123"
    head_sha = "sha-head-456"
    
    # 1. Index base repository facts into store
    repo_id = store.create_repository("github", "test-org", "test-repo")
    version_id = store.create_version(repo_id, base_sha)
    store.set_version_context(repo_id, version_id)
    
    sink = PersistentFactSink(store, repo_id, version_id)
    file_1 = File(id=FileId(1), path="app.py", language="python")
    sink.add_file(file_1)
    sym_1 = Symbol(
        id=SymbolId(1),
        name="hello",
        file_id=file_1.id,
        kind=SymbolKind.FUNCTION,
        language="python",
        start_line=1,
        end_line=5,
    )
    sink.add_symbol(sym_1)
    sink.flush()
    
    # Mock Repository Provider that only fetches changed files (lazy retrieval)
    class MockProvider:
        async def fetch_file(self, repository, file_path, sha):
            if file_path == "app.py":
                return "def hello():\n    return 'world_modified'\n"
            return None

    pipeline = Pipeline(
        repository_store=store,
        repository_provider=MockProvider(),
    )
    
    # 2. Construct AnalysisRequest
    repo_ref = RepositoryReference(
        provider="github",
        owner="test-org",
        repository="test-repo",
        default_branch=base_sha,
    )
    pr_ref = PullRequestReference(
        number=101,
        base_sha=base_sha,
        head_sha=head_sha,
        title="Test PR",
    )
    hunk = DiffHunk(
        file_path="app.py",
        source_start=1,
        source_length=5,
        target_start=1,
        target_length=5,
        added_lines=("+    return 'world_modified'",),
        removed_lines=("-    return 'world'",),
        lines=(" def hello():", "+    return 'world_modified'"),
    )
    diff_file = DiffFile(
        file_path="app.py",
        added_lines=("+    return 'world_modified'",),
        removed_lines=("-    return 'world'",),
        hunks=(hunk,),
    )
    diff_snapshot = DiffSnapshot(files=(diff_file,))
    
    request = AnalysisRequest(
        repository=repo_ref,
        pull_request=pr_ref,
        diff=diff_snapshot,
        trigger=AnalysisTrigger.MANUAL,
    )
    
    # 3. Run pipeline
    context = await pipeline.run(request)
    
    # 4. Verify invariants
    assert context.error is None
    assert context.base_repository_model is None
    assert context.head_repository_model is None
    assert context.base_query is not None
    assert context.repository_view is not None
    assert context.change_facts is not None
    assert context.impact_surface is not None
    assert context.ocm is not None
    assert context.review_context is not None
    
    # Verify symbols from overlay view
    view_syms = context.repository_view.get_symbols_in_file(FileId(1))
    assert len(view_syms) >= 1
    assert view_syms[0].name == "hello"
