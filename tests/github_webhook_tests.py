from __future__ import annotations

import hashlib
import hmac

from fastapi.testclient import TestClient

from api import main
from source_adapters.github.event_handler import build_pull_request_analysis_job, should_process_pull_request_event
from source_adapters.github.webhook import verify_github_webhook_signature


def test_github_webhook_builds_job_payload() -> None:
    job = build_pull_request_analysis_job(
        {
            "action": "opened",
            "installation": {"id": 12345},
            "repository": {
                "owner": {"login": "octo"},
                "name": "example",
                "full_name": "octo/example",
            },
            "pull_request": {"number": 42, "head": {"sha": "abc123"}},
        }
    )

    assert job.installation_id == 12345
    assert job.full_name == "octo/example"
    assert job.pr_number == 42
    assert job.head_sha == "abc123"


def test_github_webhook_event_filter() -> None:
    assert should_process_pull_request_event("pull_request", "opened")
    assert not should_process_pull_request_event("issues", "opened")


def test_github_webhook_signature_validation() -> None:
    payload = b'{"hello":"world"}'
    secret = "super-secret"
    signature = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    assert verify_github_webhook_signature(payload, signature, secret)
    assert not verify_github_webhook_signature(payload, "sha256=deadbeef", secret)


def test_github_webhook_endpoint_dispatches_analysis(monkeypatch) -> None:
    captured_jobs: list[object] = []

    monkeypatch.setattr(main.settings, "github_access_token", "token")
    monkeypatch.setattr(main.settings, "github_webhook_secret", "")
    monkeypatch.setattr(main, "schedule_pull_request_analysis", lambda background_tasks, job: captured_jobs.append(job))

    client = TestClient(main.app)
    response = client.post(
        "/github/webhook",
        headers={"X-GitHub-Event": "pull_request"},
        json={
            "action": "opened",
            "installation": {"id": 12345},
            "repository": {
                "owner": {"login": "octo"},
                "name": "example",
                "full_name": "octo/example",
            },
            "pull_request": {"number": 42, "head": {"sha": "abc123"}},
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "installation_id": 12345,
        "owner": "octo",
        "repo": "example",
        "pr_number": 42,
        "action": "opened",
        "delivery_id": None,
    }
    assert len(captured_jobs) == 1
    assert captured_jobs[0].full_name == "octo/example"
    assert captured_jobs[0].pr_number == 42


def test_github_webhook_endpoint_ignores_non_pull_request_events(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "github_access_token", "token")
    monkeypatch.setattr(main.settings, "github_webhook_secret", "")

    client = TestClient(main.app)
    response = client.post(
        "/github/webhook",
        headers={"X-GitHub-Event": "ping"},
        json={"zen": "keep it logically awesome"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
