import pytest

from integrations.base import (
    RepositoryAcquisitionMode,
    RepositoryBlob,
    RepositoryCommit,
    RepositoryTreeEntry,
)


def test_repository_models():
    commit = RepositoryCommit(sha="sha", repository="owner/repo", message="msg", author="auth")
    assert commit.sha == "sha"
    assert commit.repository == "owner/repo"
    assert commit.message == "msg"
    assert commit.author == "auth"
    
    # Check frozen dataclass properties
    with pytest.raises(AttributeError):
        commit.sha = "new_sha"  # type: ignore
        
    entry = RepositoryTreeEntry(path="src/foo.py", type="blob", sha="sha", size=100)
    assert entry.path == "src/foo.py"
    assert entry.type == "blob"
    assert entry.sha == "sha"
    assert entry.size == 100
    
    blob = RepositoryBlob(path="src/foo.py", sha="sha", size=100, content=b"content")
    assert blob.path == "src/foo.py"
    assert blob.sha == "sha"
    assert blob.size == 100
    assert blob.content == b"content"
    
    assert RepositoryAcquisitionMode.ZIP == "zip"
    assert RepositoryAcquisitionMode.GIT == "git"
