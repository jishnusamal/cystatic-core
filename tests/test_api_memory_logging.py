"""Unit tests for request and task memory logging middleware and wrappers."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.main import app
from api.routes.github import _process_pr_analysis
from core.logging import pipeline_logger


@pytest.fixture(scope="module")
def dummy_routes():
    # Register dummy endpoints for testing request flow
    @app.get("/test-memory-logging")
    def dummy():
        return {"status": "ok"}

    @app.get("/test-memory-logging-fail")
    def dummy_fail():
        raise ValueError("Simulated route error")


def test_api_memory_logging_middleware(monkeypatch, dummy_routes):
    logged_messages = []

    def mock_log_pipeline(msg, to_terminal=False):
        logged_messages.append(msg)

    monkeypatch.setattr(pipeline_logger, "log_pipeline", mock_log_pipeline)

    client = TestClient(app)

    # 1. Verify excluded path doesn't log memory metrics
    response = client.get("/health")
    assert response.status_code == 200
    assert not any("[MEMORY]" in msg for msg in logged_messages)

    # 2. Verify tracked path logs memory metrics (Starting and Finished)
    logged_messages.clear()
    response = client.get("/test-memory-logging")
    assert response.status_code == 200

    start_logs = [
        msg for msg in logged_messages if "[MEMORY]" in msg and "Starting" in msg
    ]
    finished_logs = [
        msg for msg in logged_messages if "[MEMORY]" in msg and "Finished" in msg
    ]

    assert len(start_logs) == 1
    assert len(finished_logs) == 1
    assert "/test-memory-logging" in start_logs[0]
    assert "RSS=" in start_logs[0]
    assert "/test-memory-logging" in finished_logs[0]
    assert "Status=200" in finished_logs[0]
    assert "Δ=" in finished_logs[0]
    assert "Duration=" in finished_logs[0]

    # 3. Verify failed tracked path logs failure and the exception
    logged_messages.clear()
    with pytest.raises(ValueError, match="Simulated route error"):
        client.get("/test-memory-logging-fail")

    start_logs = [
        msg for msg in logged_messages if "[MEMORY]" in msg and "Starting" in msg
    ]
    failed_logs = [
        msg for msg in logged_messages if "[MEMORY]" in msg and "Failed" in msg
    ]

    assert len(start_logs) == 1
    assert len(failed_logs) == 1
    assert "/test-memory-logging-fail" in start_logs[0]
    assert "/test-memory-logging-fail" in failed_logs[0]
    assert "Error=ValueError" in failed_logs[0]
    assert "Δ=" in failed_logs[0]
    assert "Duration=" in failed_logs[0]


@pytest.mark.asyncio
async def test_process_pr_analysis_memory_logging(monkeypatch):
    logged_messages = []

    def mock_log_pipeline(msg, to_terminal=False):
        logged_messages.append(msg)

    monkeypatch.setattr(pipeline_logger, "log_pipeline", mock_log_pipeline)

    # Mock pipeline and registry instances
    mock_pipeline = MagicMock()
    mock_pipeline.run = AsyncMock(
        return_value=MagicMock(error=None, review_context=None, ocm=None)
    )
    mock_registry = MagicMock()

    monkeypatch.setattr("api.routes.github.get_pipeline_instance", lambda: mock_pipeline)
    monkeypatch.setattr("api.routes.github.get_registry_instance", lambda: mock_registry)

    # Mock settings to make sure MEMORY_PROFILING is False by default during this test
    mock_settings = MagicMock()
    mock_settings.MEMORY_PROFILING = False
    monkeypatch.setattr("core.config.get_settings", lambda: mock_settings)

    # Create dummy AnalysisRequest
    mock_request = MagicMock()
    mock_request.repository.full_name = "test/repo"

    # Call background task handler
    await _process_pr_analysis(
        request=mock_request, installation_id=None, delivery_id="test-delivery-id"
    )

    # Verify memory logs for background task
    task_started_logs = [
        msg
        for msg in logged_messages
        if "[MEMORY][task=test-delivery-id]" in msg and "started" in msg
    ]
    task_finished_logs = [
        msg
        for msg in logged_messages
        if "[MEMORY][task=test-delivery-id]" in msg and "finished" in msg
    ]

    assert len(task_started_logs) == 1
    assert len(task_finished_logs) == 1
    assert "Background analysis started" in task_started_logs[0]
    assert "Background analysis finished" in task_finished_logs[0]
    assert "RSS=" in task_started_logs[0]
    assert "Δ=" in task_finished_logs[0]
    assert "Duration=" in task_finished_logs[0]
