"""Narrative Parser — parses LLM JSON into GithubCommentNarrative.

The LLM only generates text fields. This parser extracts those text fields
and creates a GithubCommentNarrative that can be merged with GithubCommentContext.

No metrics, no counts, no deterministic data in the output.
"""

from __future__ import annotations

import json
import re
from typing import Any

from presentation.llm.narrative_models import GithubCommentNarrative, NarrativeSurprisingDiscovery


class NarrativeParser:
    """
    Parses LLM JSON responses into GithubCommentNarrative models.
    
    The LLM output schema contains ONLY text fields:
    - executive_summary
    - review_priority
    - biggest_surprise
    - execution_summary
    - operational_summary
    - validation_summary
    - attention
    - surprising_discoveries[].explanation
    - evidence[]
    
    No metrics, no counts, no nested execution/operational/validation sections.
    """
    
    # Maximum lengths for string fields
    MAX_LENGTHS = {
        "executive_summary": 500,
        "review_priority": 300,
        "biggest_surprise": 300,
        "execution_summary": 500,
        "operational_summary": 500,
        "validation_summary": 500,
        "attention": 500,
    }
    
    # Maximum counts
    MAX_SURPRISING_DISCOVERIES = 5
    MAX_EVIDENCE_ITEMS = 10
    
    def parse(self, raw_response: str) -> GithubCommentNarrative:
        """
        Parse raw LLM response into GithubCommentNarrative.
        
        Args:
            raw_response: Raw text response from LLM
            
        Returns:
            GithubCommentNarrative with only text fields
            
        Raises:
            ValueError: If response cannot be parsed
        """
        try:
            # Step 1: Extract JSON from response
            json_data = self._extract_json(raw_response)
            
            # Step 2: Extract text fields
            narrative = GithubCommentNarrative(
                executive_summary=self._get_text(json_data, "executive_summary"),
                review_priority=self._get_text(json_data, "review_priority"),
                biggest_surprise=self._get_text(json_data, "biggest_surprise"),
                execution_summary=self._get_text(json_data, "execution_summary"),
                operational_summary=self._get_text(json_data, "operational_summary"),
                validation_summary=self._get_text(json_data, "validation_summary"),
                attention=self._get_text(json_data, "attention"),
                surprising_discoveries=self._parse_discoveries(json_data),
                evidence=self._parse_evidence(json_data),
            )
            
            return narrative
            
        except Exception as exc:
            raise ValueError(f"Failed to parse LLM narrative: {exc}") from exc
    
    def _extract_json(self, raw_response: str) -> dict[str, Any]:
        """Extract JSON from LLM response."""
        # Try to find JSON in markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON object
            json_match = re.search(r'(\{.*\})', raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = raw_response
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in LLM response: {exc}") from exc
    
    def _get_text(self, data: dict[str, Any], field: str) -> str:
        """Extract and truncate a text field."""
        value = data.get(field, "")
        if not isinstance(value, str):
            value = str(value) if value is not None else ""
        
        max_length = self.MAX_LENGTHS.get(field, 500)
        if len(value) > max_length:
            value = value[:max_length - 3] + "..."
        
        return value
    
    def _parse_discoveries(self, data: dict[str, Any]) -> tuple[NarrativeSurprisingDiscovery, ...]:
        """Parse surprising discoveries from LLM response."""
        discoveries_raw = data.get("surprising_discoveries", [])
        if not isinstance(discoveries_raw, list):
            return ()
        
        discoveries = []
        for item in discoveries_raw[:self.MAX_SURPRISING_DISCOVERIES]:
            if isinstance(item, dict):
                discoveries.append(NarrativeSurprisingDiscovery(
                    explanation=self._get_text(item, "explanation"),
                ))
        
        return tuple(discoveries)
    
    def _parse_evidence(self, data: dict[str, Any]) -> tuple[str, ...]:
        """Parse evidence items from LLM response."""
        evidence_raw = data.get("evidence", [])
        if not isinstance(evidence_raw, list):
            return ()
        
        evidence = []
        for item in evidence_raw[:self.MAX_EVIDENCE_ITEMS]:
            if isinstance(item, str):
                evidence.append(item[:200])  # Truncate long evidence
            elif item is not None:
                evidence.append(str(item)[:200])
        
        return tuple(evidence)
    
    def create_fallback_narrative(self, error: Exception) -> GithubCommentNarrative:
        """
        Create a fallback narrative when LLM parsing fails.
        
        Returns an empty narrative — the context builder's diagnostic context
        will provide the fallback text.
        """
        return GithubCommentNarrative()