"""Render GitHub PR comments for Factor findings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def render_pull_request_comment(result: dict[str, Any]) -> str:
    env = Environment(loader=FileSystemLoader(BASE_DIR / "templates"))
    template: Template = env.get_template("github/pr_comment.md.j2")

    failure_simulation = result.get("failure_simulation") or {}

    return template.render(
        verdict=result.get("verdict", "UNKNOWN"),
        failure_simulation=failure_simulation,
    )
