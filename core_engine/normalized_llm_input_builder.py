"""
Normalized LLM Input Builder — builds reviewer-ready input from LlmFacts.

This module is the ONLY interface between the deterministic engine and the LLM.

It uses ReviewerFactsBuilder to produce a CompactPacket — a compact, structured
feature packet (~1.2k–1.8k tokens) where every token contributes meaningful
engineering context.

Target budget: ≤2,000 tokens for llm_input.
"""
from __future__ import annotations

from typing import Any

from core_engine.llm_facts import LlmFacts
from core_engine.llm_facts.reviewer_facts_builder import ReviewerFactsBuilder


def build_normalized_llm_input(
    llm_facts: LlmFacts,
    repo: str = "",
    pr_number: int = 0,
) -> dict[str, Any]:
    """Build LLM input from deterministic facts using ReviewerFactsBuilder.

    The LLM receives a CompactPacket — a compact, structured feature packet
    with symbol IDs, feature flags, graph edges, and compressed summaries.

    Args:
        llm_facts: LlmFacts from the deterministic engine.
        repo: Repository name.
        pr_number: PR number.

    Returns:
        A dict containing the compact reviewer packet.
    """
    builder = ReviewerFactsBuilder(
        llm_facts,
        repo=repo,
        pr_number=pr_number,
    )
    packet = builder.build()
    return packet.to_dict()


def build_llm_input_from_facts(
    llm_facts: LlmFacts,
) -> dict[str, Any]:
    """Build LLM input directly from LlmFacts."""
    return build_normalized_llm_input(
        llm_facts=llm_facts,
        repo=llm_facts.repo,
        pr_number=llm_facts.pr_number,
    )