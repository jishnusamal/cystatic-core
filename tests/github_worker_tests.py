from __future__ import annotations

from types import SimpleNamespace

from source_adapters.github.event_handler import PullRequestAnalysisJob
from workers import analyze_pr


def test_process_pull_request_job_posts_comment(monkeypatch) -> None:
    published: list[tuple[str, int, str]] = []

    class FakePublisher:
        def post_comment(self, repo: str, pr_number: int, comment: str) -> None:
            published.append((repo, pr_number, comment))

    class FakeOrchestrator:
        def __init__(self, **kwargs) -> None:
            self.request = kwargs["request"]

        def run_pr_analysis(self):
            return {"verdict": "SAFE", "failure_simulation": {"verdict": "SAFE"}}

        async def log_run(self, result):
            return None

    monkeypatch.setattr(
        analyze_pr,
        "get_settings",
        lambda: SimpleNamespace(
            github_app_id="app-123",
            github_private_key="-----BEGIN RSA PRIVATE KEY-----\nkey\n-----END RSA PRIVATE KEY-----",
            github_client_secret="",
            llm_api_key="",
            ai_api_key="",
            llm_model="openai/gpt-oss-120b",
            llm_base_url="https://api.groq.com/openai/v1",
            app_env="",
        ),
    )
    monkeypatch.setattr(analyze_pr, "get_installation_token", lambda app_id, private_key, installation_id: "installation_token")
    monkeypatch.setattr(analyze_pr, "build_github_clients", lambda token: (object(), FakePublisher()))
    monkeypatch.setattr(analyze_pr, "Orchestrator", FakeOrchestrator)
    monkeypatch.setattr(analyze_pr, "render_pull_request_comment", lambda result: "comment body")

    result = analyze_pr.process_pull_request_job(
        PullRequestAnalysisJob(
            installation_id=12345,
            owner="octo",
            repo="example",
            pr_number=42,
            action="opened",
        )
    )

    assert result["verdict"] == "SAFE"
    assert published == [("octo/example", 42, "comment body")]
