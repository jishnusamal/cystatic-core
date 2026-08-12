"""Comprehensive test suite for Factor Logging Infrastructure v2."""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
import pytest

from core.runtime.run_id import generate_run_id
from core.runtime.run_context import RunContext
from core.runtime.log_manager import LogManager
from core.logging import pipeline_logger


def test_run_id_generation():
    dt = datetime(2026, 7, 22, 10, 41, 55)
    run_id = generate_run_id(dt)
    
    # Matching run-YYYYMMDD-HHMMSS-random6 format
    assert re.match(r"^run-20260722-104155-[0-9a-f]{6}$", run_id)
    
    # Lexicographical sortability test
    dt1 = datetime(2026, 7, 22, 10, 41, 55)
    dt2 = datetime(2026, 7, 22, 10, 41, 56)
    id1 = generate_run_id(dt1)
    id2 = generate_run_id(dt2)
    assert id1 < id2
    
    # Uniqueness
    id_a = generate_run_id()
    id_b = generate_run_id()
    assert id_a != id_b


def test_run_context_immutability(tmp_path):
    ctx = RunContext.create(base_dir=tmp_path)
    assert ctx.run_id.startswith("run-")
    assert ctx.log_dir.exists()
    assert ctx.log_manager is not None
    
    with pytest.raises(Exception):
        ctx.run_id = "modified"  # frozen dataclass check


def test_log_manager_live_streaming(tmp_path):
    log_dir = tmp_path / "test_run"
    mgr = LogManager(log_dir=log_dir, run_id="test_run")
    
    # Test immediate flushing
    mgr.log_pipeline("pipeline msg 1", to_terminal=False)
    mgr.log_visitor("visitor msg 1", to_terminal=False)
    mgr.log_semantic("semantic msg 1", to_terminal=False)
    mgr.log_resolver("resolver msg 1", to_terminal=False)
    mgr.log_performance("performance msg 1", to_terminal=False)
    
    pipeline_file = log_dir / "pipeline.log"
    visitor_file = log_dir / "visitor.log"
    semantic_file = log_dir / "semantic.log"
    resolver_file = log_dir / "resolver.log"
    performance_file = log_dir / "performance.log"
    
    assert pipeline_file.exists()
    assert "pipeline msg 1" in pipeline_file.read_text()
    assert "visitor msg 1" in visitor_file.read_text()
    assert "semantic msg 1" in semantic_file.read_text()
    assert "resolver msg 1" in resolver_file.read_text()
    assert "performance msg 1" in performance_file.read_text()
    
    mgr.close()


def test_log_manager_structured_json(tmp_path):
    log_dir = tmp_path / "test_run"
    mgr = LogManager(log_dir=log_dir, run_id="test_run")
    
    data = {"metric": "latency", "value": 42.5}
    mgr.write_json("summary.json", data)
    
    summary_file = log_dir / "summary.json"
    assert summary_file.exists()
    read_data = json.loads(summary_file.read_text())
    assert read_data["metric"] == "latency"
    assert read_data["value"] == 42.5
    
    mgr.close()


def test_failure_logging(tmp_path):
    log_dir = tmp_path / "fail_run"
    mgr = LogManager(log_dir=log_dir, run_id="fail_run")
    
    try:
        raise ValueError("Simulated pipeline failure")
    except ValueError as exc:
        mgr.log_failure(
            exc=exc,
            phase="semantic",
            repository="owner/repo",
            pr="123",
            elapsed_time=1.42,
        )
    
    pipeline_file = log_dir / "pipeline.log"
    content = pipeline_file.read_text()
    assert "ERROR ANALYSIS FAILURE" in content
    assert "Simulated pipeline failure" in content
    assert "Phase:        semantic" in content
    assert "Repository:   owner/repo" in content
    assert "PR:           123" in content
    assert "Run ID:       fail_run" in content
    
    mgr.close()


def test_concurrent_run_isolation(tmp_path):
    ctx1 = RunContext.create(base_dir=tmp_path)
    ctx2 = RunContext.create(base_dir=tmp_path)
    
    assert ctx1.run_id != ctx2.run_id
    assert ctx1.log_dir != ctx2.log_dir
    
    ctx1.log_manager.log_pipeline("Run 1 exclusive message", to_terminal=False)
    ctx2.log_manager.log_pipeline("Run 2 exclusive message", to_terminal=False)
    
    content1 = (ctx1.log_dir / "pipeline.log").read_text()
    content2 = (ctx2.log_dir / "pipeline.log").read_text()
    
    assert "Run 1 exclusive message" in content1
    assert "Run 1 exclusive message" not in content2
    assert "Run 2 exclusive message" in content2
    assert "Run 2 exclusive message" not in content1
    
    ctx1.log_manager.close()
    ctx2.log_manager.close()
