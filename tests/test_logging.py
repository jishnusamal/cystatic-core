"""Integration tests for run-scoped live-streaming logging architecture v2."""

import os
from unittest.mock import MagicMock

import pytest

from engine.pipeline.pipeline import Pipeline
from engine.repository.indexing import MemoryRepositoryStore
from integrations.base import RepositoryProvider
from models.analysis import (
    AnalysisRequest,
    AnalysisTrigger,
    PullRequestReference,
    RepositoryReference,
)


class MockRepositoryProvider(RepositoryProvider):
    async def fetch_repository(self, repo_ref):
        return MagicMock()

    async def fetch_repository_at_sha(self, repository, sha):
        snapshot = MagicMock()
        snapshot.files = {
            "main.py": "from utils import greet\ngreet()\n",
            "utils.py": "def greet():\n    print('hello')\n",
        }
        return snapshot

    async def fetch_diff(self, repository, base_sha, head_sha):
        return MagicMock()

    async def fetch_file(self, repo_ref, file_path, sha):
        return ""

    async def fetch_tree(self, repo_ref, sha):
        return {}

    async def fetch_commit(self, repo_ref, sha):
        return {}


@pytest.mark.asyncio
async def test_pipeline_logging():
    pipeline = Pipeline(
        repository_provider=MockRepositoryProvider(),
        repository_store=MemoryRepositoryStore(),
    )

    request = AnalysisRequest(
        repository=RepositoryReference(
            provider="github",
            owner="test",
            repository="repo",
            default_branch="main",
        ),
        pull_request=PullRequestReference(
            number=1,
            base_sha="base",
            head_sha="head",
            title="Test PR",
        ),
        trigger=AnalysisTrigger.MANUAL,
    )

    context = await pipeline.run(request)

    assert context.run_context is not None
    log_dir = context.run_context.log_dir

    # Verify run ID format (run-YYYYMMDD-HHMMSS-******)
    assert context.run_context.run_id.startswith("run-")
    assert len(context.run_context.run_id.split("-")) == 4

    # Verify directory and files
    assert os.path.exists(log_dir)
    assert os.path.exists(os.path.join(log_dir, "pipeline.log"))
    assert os.path.exists(os.path.join(log_dir, "visitor.log"))
    assert os.path.exists(os.path.join(log_dir, "semantic.log"))
    assert os.path.exists(os.path.join(log_dir, "resolver.log"))
    assert os.path.exists(os.path.join(log_dir, "performance.log"))
    assert os.path.exists(os.path.join(log_dir, "timings.json"))
    assert os.path.exists(os.path.join(log_dir, "summary.json"))
    assert os.path.exists(os.path.join(log_dir, "profile.json"))
    assert os.path.exists(os.path.join(log_dir, "call_resolution.json"))

    # Verify contents
    with open(os.path.join(log_dir, "pipeline.log"), "r") as f:
        pipeline_log = f.read()
        assert "[pipeline]" in pipeline_log
        assert "Factor Analysis" in pipeline_log
        assert context.run_context.run_id in pipeline_log
