"""Dramatiq job definitions for analysis tasks.

TODO: Wire up dramatiq actors for background analysis.
"""

from __future__ import annotations

# TODO: Define dramatiq actors
# import dramatiq
# from workers.queue import broker
#
# @dramatiq.actor(queue_name="analysis")
# def analyze_pr_job(repo: str, pr_number: int, installation_id: str) -> None:
#     from workers.analyze_pr import process_pr_analysis
#     process_pr_analysis(repo, pr_number, installation_id)
