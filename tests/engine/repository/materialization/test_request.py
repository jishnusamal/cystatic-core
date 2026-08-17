from dataclasses import FrozenInstanceError
import pytest
from engine.repository.materialization.request import MaterializationRequest

def test_materialization_request_creation():
    request = MaterializationRequest(
        repository_id="github/testowner/testrepo",
        commit_sha="1234567890abcdef",
        paths=("a.py", "b.py"),
        reason="import_resolution",
    )
    assert request.repository_id == "github/testowner/testrepo"
    assert request.commit_sha == "1234567890abcdef"
    assert request.paths == ("a.py", "b.py")
    assert request.reason == "import_resolution"

def test_materialization_request_immutability():
    request = MaterializationRequest(
        repository_id="github/testowner/testrepo",
        commit_sha="1234567890abcdef",
        paths=("a.py",),
        reason="caller_resolution",
    )
    with pytest.raises(FrozenInstanceError):
        request.reason = "new_reason"  # type: ignore
