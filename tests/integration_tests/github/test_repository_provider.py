import base64
import json
from unittest.mock import MagicMock

import pytest
import requests

from core.errors import (
    CommitNotFound,
    FileNotFound,
    PartialBatchFailure,
    TreeTruncated,
)
from integrations.base import (
    RepositoryAcquisitionMode,
)
from integrations.github.repositories import GitHubRepositoryProvider


def make_mock_response(status_code, json_data=None, text_content=None, headers=None):
    res = MagicMock(spec=requests.Response)
    res.status_code = status_code
    res.headers = headers or {}
    res.text = text_content or ""
    if json_data is not None:
        res.json.return_value = json_data
        res.text = json.dumps(json_data)
        res.content = json.dumps(json_data).encode("utf-8")
    elif text_content is not None:
        res.content = text_content.encode("utf-8")
    else:
        res.content = b""
        
    if status_code >= 400:
        http_error = requests.HTTPError(response=res)
        res.raise_for_status.side_effect = http_error
    else:
        res.raise_for_status.return_value = None
    return res

def make_mock_router(commit_data=None, tree_data=None, blob_responses=None, file_meta_response=None):
    def route_get(path, **kwargs):
        if "commits/" in path and commit_data is not None:
            return make_mock_response(200, json_data=commit_data)
        if "git/trees/" in path and tree_data is not None:
            return make_mock_response(200, json_data=tree_data)
        if "git/blobs/" in path:
            sha = path.split("/")[-1]
            if blob_responses and sha in blob_responses:
                return make_mock_response(200, json_data=blob_responses[sha])
        if "contents/" in path and file_meta_response is not None:
            return make_mock_response(200, json_data=file_meta_response)
        return make_mock_response(404)
    return route_get

@pytest.fixture(autouse=True)
def mock_get_settings(monkeypatch):
    class MockSettings:
        GITHUB_ACCESS_TOKEN = "mock_token"
        REPOSITORY_ACQUISITION_MODE = "zip"
        GITHUB_MAX_CONCURRENT_BLOB_REQUESTS = 10
    monkeypatch.setattr("core.config.get_settings", lambda: MockSettings())

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.close.return_value = None
    return client

@pytest.fixture
def provider(mock_client):
    prov = GitHubRepositoryProvider()
    prov._get_client = MagicMock(return_value=mock_client)
    return prov

@pytest.mark.asyncio
async def test_get_commit_success(provider, mock_client):
    commit_data = {
        "sha": "abc123commit",
        "commit": {
            "message": "feat: init",
            "author": {"name": "Alice"},
        }
    }
    mock_client.get.side_effect = make_mock_router(commit_data=commit_data)
    commit = await provider.get_commit("owner/repo", "abc123commit")
    assert commit.sha == "abc123commit"
    assert commit.repository == "owner/repo"
    assert commit.message == "feat: init"
    assert commit.author == "Alice"
    mock_client.get.assert_called_once_with(
        "/repos/owner/repo/commits/abc123commit",
        headers={"Accept": "application/vnd.github+json"},
        timeout=30,
    )

@pytest.mark.asyncio
async def test_get_commit_not_found(provider, mock_client):
    mock_client.get.side_effect = lambda path, **kwargs: make_mock_response(404)
    with pytest.raises(CommitNotFound):
        await provider.get_commit("owner/repo", "missing_sha")

@pytest.mark.asyncio
async def test_get_tree_success(provider, mock_client):
    tree_data = {
        "sha": "treesha",
        "truncated": False,
        "tree": [
            {"path": "src/foo.py", "type": "blob", "sha": "blob1", "size": 100},
            {"path": "src/bar.py", "type": "blob", "sha": "blob2", "size": 200},
            {"path": "src/dir", "type": "tree", "sha": "treesha2"},
            {"path": "submodule", "type": "commit", "sha": "subsha"},
        ]
    }
    mock_client.get.side_effect = make_mock_router(tree_data=tree_data)
    entries = await provider.get_tree("owner/repo", "abc123commit")
    assert len(entries) == 3
    assert entries[0].path == "src/foo.py"
    assert entries[0].type == "blob"
    assert entries[0].sha == "blob1"
    assert entries[0].size == 100
    
    assert entries[2].path == "src/dir"
    assert entries[2].type == "tree"
    assert entries[2].sha == "treesha2"

@pytest.mark.asyncio
async def test_get_tree_truncated(provider, mock_client):
    tree_data = {
        "sha": "treesha",
        "truncated": True,
        "tree": []
    }
    mock_client.get.side_effect = make_mock_router(tree_data=tree_data)
    with pytest.raises(TreeTruncated):
        await provider.get_tree("owner/repo", "abc123commit")

@pytest.mark.asyncio
async def test_get_file_success(provider, mock_client):
    file_meta = {
        "type": "file",
        "sha": "blobsha",
        "size": 12,
    }
    blob_res = {
        "sha": "blobsha",
        "content": base64.b64encode(b"hello world\n").decode("utf-8"),
        "encoding": "base64",
    }
    mock_client.get.side_effect = make_mock_router(
        file_meta_response=file_meta,
        blob_responses={"blobsha": blob_res}
    )
    blob = await provider.get_file("owner/repo", "src/foo.py", "abc123commit")
    assert blob.path == "src/foo.py"
    assert blob.sha == "blobsha"
    assert blob.size == 12
    assert blob.content == b"hello world\n"

@pytest.mark.asyncio
async def test_get_file_not_found(provider, mock_client):
    mock_client.get.side_effect = lambda path, **kwargs: make_mock_response(404)
    with pytest.raises(FileNotFound):
        await provider.get_file("owner/repo", "src/missing.py", "ref")

@pytest.mark.asyncio
async def test_get_files_success(provider, mock_client):
    tree_data = {
        "truncated": False,
        "tree": [
            {"path": "src/foo.py", "type": "blob", "sha": "sha1", "size": 10},
            {"path": "src/bar.py", "type": "blob", "sha": "sha2", "size": 20},
        ]
    }
    blob_responses = {
        "sha1": {"content": base64.b64encode(b"foo content").decode("utf-8")},
        "sha2": {"content": base64.b64encode(b"bar content").decode("utf-8")},
    }
    mock_client.get.side_effect = make_mock_router(
        tree_data=tree_data,
        blob_responses=blob_responses
    )
    
    blobs = await provider.get_files("owner/repo", ["src/foo.py", "src/bar.py", "src/foo.py"], "ref")
    
    assert len(blobs) == 2
    assert blobs[0].path == "src/bar.py"
    assert blobs[0].content == b"bar content"
    assert blobs[1].path == "src/foo.py"
    assert blobs[1].content == b"foo content"

@pytest.mark.asyncio
async def test_get_files_partial_failure(provider, mock_client):
    tree_data = {
        "truncated": False,
        "tree": [
            {"path": "src/foo.py", "type": "blob", "sha": "sha1", "size": 10},
            {"path": "src/bar.py", "type": "blob", "sha": "sha2", "size": 20},
        ]
    }
    blob_responses = {
        "sha1": {"content": base64.b64encode(b"foo content").decode("utf-8")},
    }
    mock_client.get.side_effect = make_mock_router(
        tree_data=tree_data,
        blob_responses=blob_responses
    )
    
    with pytest.raises(PartialBatchFailure) as exc_info:
        await provider.get_files("owner/repo", ["src/foo.py", "src/bar.py", "src/missing.py"], "ref")
        
    err = exc_info.value
    assert len(err.successes) == 1
    assert err.successes[0].path == "src/foo.py"
    
    assert "src/bar.py" in err.failures
    assert "src/missing.py" in err.failures
    assert isinstance(err.failures["src/missing.py"], FileNotFound)

@pytest.mark.asyncio
async def test_vertical_acceptance_no_zip(provider, mock_client):
    commit_data = {
        "sha": "base_sha",
        "commit": {
            "message": "PR base",
            "author": {"name": "Dev"},
        }
    }
    tree_data = {
        "truncated": False,
        "tree": [
            {"path": "src/foo.py", "type": "blob", "sha": "sha1", "size": 10},
            {"path": "src/bar.py", "type": "blob", "sha": "sha2", "size": 20},
        ]
    }
    blob_responses = {
        "sha1": {"content": base64.b64encode(b"updated foo").decode("utf-8")},
    }
    mock_client.get.side_effect = make_mock_router(
        commit_data=commit_data,
        tree_data=tree_data,
        blob_responses=blob_responses
    )
    
    commit = await provider.get_commit("PostHog/posthog", "base_sha")
    assert commit.sha == "base_sha"
    
    tree = await provider.get_tree("PostHog/posthog", "base_sha")
    assert len(tree) == 2
    
    changed_paths = ["src/foo.py"]
    files = await provider.get_files(
        repository="PostHog/posthog",
        paths=changed_paths,
        ref="base_sha",
    )
    
    assert len(files) == 1
    assert files[0].path == "src/foo.py"
    assert files[0].content == b"updated foo"
    
    for call in mock_client.get.call_args_list:
        path_called = call[0][0]
        assert "zipball" not in path_called

@pytest.mark.asyncio
async def test_fetch_repository_at_sha_git_mode(mock_client):
    prov = GitHubRepositoryProvider(acquisition_mode=RepositoryAcquisitionMode.GIT)
    
    commit_data = {
        "sha": "git_sha",
        "commit": {
            "message": "Commit message",
            "author": {"name": "Developer"},
        }
    }
    tree_data = {
        "truncated": False,
        "tree": [
            {"path": "main.py", "type": "blob", "sha": "sha1", "size": 10},
        ]
    }
    blob_responses = {
        "sha1": {"content": base64.b64encode(b"main content").decode("utf-8")},
    }
    mock_client.get.side_effect = make_mock_router(
        commit_data=commit_data,
        tree_data=tree_data,
        blob_responses=blob_responses
    )
    
    prov._get_client = MagicMock(return_value=mock_client)
    
    from models.core import RepositoryReference
    repo_ref = RepositoryReference(provider="github", owner="owner", repository="repo")
    
    snapshot = await prov.fetch_repository_at_sha(repo_ref, "git_sha")
    
    assert snapshot.commit == "git_sha"
    assert snapshot.files == {"main.py": "main content"}
    assert len(snapshot.tree["tree"]) == 1
    assert snapshot.tree["tree"][0]["path"] == "main.py"
