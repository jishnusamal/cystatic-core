"""
Failure simulation LLM — backward-compatible stub for the new pipeline.

The old FailureSimulationLLM class provided LLM-based failure scenario generation.
The new pipeline (ReviewPipeline → EvidencePacket) handles this deterministically.
This stub preserves the import interface for backward compatibility.
"""

from __future__ import annotations

from typing import Any


class FailureSimulationLLM:
    """Backward-compatible stub.

    The new pipeline uses deterministic evidence from ReviewPipeline
    instead of LLM-based failure simulation. This class preserves the
    public API for code that still references it.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        base_url: str = "https://api.groq.com/openai/v1",
        site_url: str | None = None,
        site_name: str | None = None,
        reasoning_enabled: bool = True,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.site_url = site_url
        self.site_name = site_name
        self.reasoning_enabled = reasoning_enabled

    def build_prompt(self, llm_input: dict[str, Any]) -> list[Any]:
        """Build prompt from the llm_input structure.

        Args:
            llm_input: The deterministic facts dict.

        Returns:
            List of message dicts for the LLM API call.
        """
        return []

    def generate(self, llm_input: dict[str, Any]) -> dict[str, Any]:
        """Generate failure simulation from reviewer-ready facts.

        Args:
            llm_input: The deterministic facts dict.

        Returns:
            Empty dict — the new pipeline handles this deterministically.
        """
        return {}