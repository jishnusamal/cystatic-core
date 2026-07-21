"""Integration tests for three-level logging and profiling."""

import os
import shutil
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from runtime.pipeline.pipeline import Pipeline
from runtime.models import AnalysisRequest, RepositoryReference, PullRequestReference, AnalysisTrigger
from runtime.storage.repository_store import MemoryRepositoryStore
from integrations.base import RepositoryProvider

class MockRepositoryProvider(RepositoryProvider):
    async def fetch_repository(self, repo_ref):
        return MagicMock()

    async def fetch_repository_at_sha(self, repository, sha):
        snapshot = MagicMock()
        snapshot.files = {
            "main.py": "from utils import greet\ngreet()\n",
            "utils.py": "def greet():\n    print('hello')\n"
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
    # Clean up logs directory if any
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_dir = os.path.join("logs", f"run-{date_str}")
    if os.path.exists(log_dir):
        try:
            shutil.rmtree(log_dir)
        except Exception:
            pass
        
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
    
    # Verify directory and files
    assert os.path.exists(log_dir)
    assert os.path.exists(os.path.join(log_dir, "pipeline.log"))
    assert os.path.exists(os.path.join(log_dir, "visitor_profile.txt"))
    assert os.path.exists(os.path.join(log_dir, "semantic_graph_stats.txt"))
    assert os.path.exists(os.path.join(log_dir, "timings.json"))
    assert os.path.exists(os.path.join(log_dir, "call_resolution.json"))
    
    # Verify contents
    with open(os.path.join(log_dir, "pipeline.log"), "r") as f:
        pipeline_log = f.read()
        assert "[pipeline]" in pipeline_log
        
    with open(os.path.join(log_dir, "visitor_profile.txt"), "r") as f:
        visitor_log = f.read()
        assert "VISITOR PASS SUMMARY" in visitor_log
        
    with open(os.path.join(log_dir, "semantic_graph_stats.txt"), "r") as f:
        semantic_log = f.read()
        assert "SEMANTIC COMPILATION - INPUT SIZE" in semantic_log
