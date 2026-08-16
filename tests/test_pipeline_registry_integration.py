import pytest
from unittest.mock import AsyncMock

from core.errors import LanguageDetectionFailed, LanguageNotSupported
from engine.language.builtins import create_default_language_registry
from engine.pipeline.pipeline import Pipeline
from engine.repository.store import SQLiteRepositoryStore
from models import (
    AnalysisRequest,
    AnalysisTrigger,
    DiffSnapshot,
    PullRequestReference,
    RepositoryReference,
)
from models.core import DiffFile, DiffHunk


@pytest.mark.asyncio
async def test_python_pipeline_integration():
    """Verify that a Python repository compiles end-to-end using the default registry."""
    # 1. Setup repository store and mock provider
    store = SQLiteRepositoryStore(":memory:")
    registry = create_default_language_registry()

    class MockSnapshot:
        files = {
            "app.py": "def hello():\n    return 'world'\n",
            "utils.py": "def add(a, b):\n    return a + b\n"
        }

    class MockProvider:
        async def fetch_repository_at_sha(self, repository, sha):
            return MockSnapshot()

        async def fetch_file(self, repository, file_path, sha):
            if file_path == "app.py":
                return "def hello():\n    return 'world_modified'\n"
            return None

    pipeline = Pipeline(
        repository_store=store,
        language_registry=registry,
        repository_provider=MockProvider(),
    )

    # 2. Construct AnalysisRequest
    repo_ref = RepositoryReference(
        provider="github",
        owner="test-org",
        repository="test-repo",
        default_branch="base",
    )
    pr_ref = PullRequestReference(
        number=101,
        base_sha="base",
        head_sha="head",
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
    assert context.language == "python"
    assert context.base_query is not None
    assert context.repository_view is not None
    assert context.change_facts is not None
    assert context.impact_surface is not None
    assert context.ocm is not None


@pytest.mark.asyncio
async def test_typescript_pipeline_integration():
    """Verify that a TypeScript repository is detected but creation fails as unsupported."""
    store = SQLiteRepositoryStore(":memory:")
    registry = create_default_language_registry()

    class MockSnapshot:
        files = {
            "app.ts": "const x: number = 42;",
        }

    class MockProvider:
        async def fetch_repository_at_sha(self, repository, sha):
            return MockSnapshot()

        async def fetch_file(self, repository, file_path, sha):
            return None

    pipeline = Pipeline(
        repository_store=store,
        language_registry=registry,
        repository_provider=MockProvider(),
    )

    # Construct request
    repo_ref = RepositoryReference(
        provider="github",
        owner="test-org",
        repository="test-repo",
        default_branch="base",
    )
    pr_ref = PullRequestReference(
        number=102,
        base_sha="base",
        head_sha="head",
        title="Test TS PR",
    )
    hunk = DiffHunk(
        file_path="app.ts",
        source_start=1,
        source_length=1,
        target_start=1,
        target_length=1,
        added_lines=("+const y = 43;",),
        removed_lines=("-const x: number = 42;",),
        lines=("+const y = 43;",),
    )
    diff_file = DiffFile(
        file_path="app.ts",
        added_lines=("+const y = 43;",),
        removed_lines=("-const x: number = 42;",),
        hunks=(hunk,),
    )
    diff_snapshot = DiffSnapshot(files=(diff_file,))

    request = AnalysisRequest(
        repository=repo_ref,
        pull_request=pr_ref,
        diff=diff_snapshot,
        trigger=AnalysisTrigger.MANUAL,
    )

    # Running pipeline should raise LanguageNotSupported when creating TypeScript adapter
    with pytest.raises(LanguageNotSupported) as exc_info:
        await pipeline.run(request)

    assert "typescript" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_unregistered_language_pipeline_integration():
    """Verify that an unregistered language (e.g. rust) raises LanguageDetectionFailed."""
    store = SQLiteRepositoryStore(":memory:")
    registry = create_default_language_registry()

    class MockSnapshot:
        files = {
            "main.rs": "fn main() {}",
        }

    class MockProvider:
        async def fetch_repository_at_sha(self, repository, sha):
            return MockSnapshot()

        async def fetch_file(self, repository, file_path, sha):
            return None

    pipeline = Pipeline(
        repository_store=store,
        language_registry=registry,
        repository_provider=MockProvider(),
    )

    repo_ref = RepositoryReference(
        provider="github",
        owner="test-org",
        repository="test-repo",
        default_branch="base",
    )
    pr_ref = PullRequestReference(
        number=103,
        base_sha="base",
        head_sha="head",
        title="Test Rust PR",
    )
    hunk = DiffHunk(
        file_path="main.rs",
        source_start=1,
        source_length=1,
        target_start=1,
        target_length=1,
        added_lines=("+fn main() { println!(); }",),
        removed_lines=("-fn main() {}",),
        lines=("+fn main() { println!(); }",),
    )
    diff_file = DiffFile(
        file_path="main.rs",
        added_lines=("+fn main() { println!(); }",),
        removed_lines=("-fn main() {}",),
        hunks=(hunk,),
    )
    diff_snapshot = DiffSnapshot(files=(diff_file,))

    request = AnalysisRequest(
        repository=repo_ref,
        pull_request=pr_ref,
        diff=diff_snapshot,
        trigger=AnalysisTrigger.MANUAL,
    )

    with pytest.raises(LanguageDetectionFailed):
        await pipeline.run(request)
