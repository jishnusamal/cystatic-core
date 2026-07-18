"""LLM Response Parser.

Parses raw LLM JSON responses into structured GithubComment models.
Validates schema, required fields, and data types.
Never trusts LLM output - always validates.
"""

from __future__ import annotations

import json
import re
from typing import Any

from presentation.llm.models import (
    ExecutionSection,
    GithubComment,
    OperationalSection,
    SurprisingDiscovery,
    ValidationSection,
)


class LLMResponseParser:
    """
    Parses LLM responses into structured GithubComment models.
    
    Responsibilities:
    - Extract JSON from LLM response (may contain markdown wrappers)
    - Validate required fields
    - Validate data types
    - Convert to GithubComment model
    - Provide fallback on parse failure
    
    Never trusts LLM output. Always validates structure.
    """
    
    # Store the last parsed comment for access by pipeline
    last_parsed_comment: GithubComment | None = None
    
    # Required fields for GithubComment
    REQUIRED_FIELDS = {
        "executive_summary",
        "review_priority",
        "biggest_surprise",
        "execution_summary",
        "operational_summary",
        "validation_summary",
        "attention",
    }
    
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
    
    # Maximum counts for collection fields
    MAX_SURPRISING_DISCOVERIES = 5
    MAX_EVIDENCE_ITEMS = 10
    
    def parse(self, raw_response: str) -> GithubComment:
        """
        Parse raw LLM response into GithubComment model.
        
        Args:
            raw_response: Raw text response from LLM
            
        Returns:
            Validated GithubComment model
            
        Raises:
            ValueError: If response cannot be parsed or validated
        """
        try:
            # Step 1: Extract JSON from response
            json_data = self._extract_json(raw_response)
            
            # Step 2: Validate required fields
            self._validate_required_fields(json_data)
            
            # Step 3: Validate and sanitize string fields
            json_data = self._sanitize_string_fields(json_data)
            
            # Step 4: Validate and parse nested structures
            json_data = self._parse_nested_structures(json_data)
            
            # Step 5: Create GithubComment model
            comment = GithubComment(**json_data)
            
            # Store for later access
            LLMResponseParser.last_parsed_comment = comment
            
            return comment
            
        except Exception as exc:
            raise ValueError(f"Failed to parse LLM response: {exc}") from exc
    
    def _extract_json(self, raw_response: str) -> dict[str, Any]:
        """
        Extract JSON from LLM response.
        
        LLMs may wrap JSON in markdown code blocks or add explanatory text.
        We need to find and extract just the JSON.
        """
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
                # Use entire response as JSON
                json_str = raw_response
        
        # Parse JSON
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in LLM response: {exc}") from exc
    
    def _validate_required_fields(self, json_data: dict[str, Any]) -> None:
        """Validate that all required fields are present."""
        missing_fields = self.REQUIRED_FIELDS - set(json_data.keys())
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(sorted(missing_fields))}")
    
    def _sanitize_string_fields(self, json_data: dict[str, Any]) -> dict[str, Any]:
        """Validate and truncate string fields."""
        sanitized = json_data.copy()
        
        for field_name, max_length in self.MAX_LENGTHS.items():
            if field_name in sanitized:
                value = sanitized[field_name]
                if not isinstance(value, str):
                    raise ValueError(f"Field '{field_name}' must be a string, got {type(value).__name__}")
                # Truncate if too long
                if len(value) > max_length:
                    sanitized[field_name] = value[:max_length - 3] + "..."
        
        return sanitized
    
    def _parse_nested_structures(self, json_data: dict[str, Any]) -> dict[str, Any]:
        """Parse and validate nested structures."""
        result = json_data.copy()
        
        # Parse surprising_discoveries
        if "surprising_discoveries" in result:
            discoveries = result["surprising_discoveries"]
            if not isinstance(discoveries, list):
                raise ValueError("Field 'surprising_discoveries' must be a list")
            
            parsed_discoveries = []
            for i, disc in enumerate(discoveries[:self.MAX_SURPRISING_DISCOVERIES]):
                if not isinstance(disc, dict):
                    raise ValueError(f"Discovery {i} must be a dict")
                if "title" not in disc or "explanation" not in disc:
                    raise ValueError(f"Discovery {i} missing required fields: title, explanation")
                parsed_discoveries.append(SurprisingDiscovery(
                    title=disc["title"],
                    explanation=disc["explanation"],
                    metric=disc.get("metric", ""),
                    support=disc.get("support", ""),
                ))
            result["surprising_discoveries"] = parsed_discoveries
        
        # Parse execution section
        if "execution" in result:
            exec_data = result["execution"]
            if not isinstance(exec_data, dict):
                raise ValueError("Field 'execution' must be a dict")
            
            highlights = []
            if "highlights" in exec_data:
                for disc in exec_data["highlights"][:3]:  # Max 3 highlights
                    if isinstance(disc, dict):
                        highlights.append(SurprisingDiscovery(
                            title=disc.get("title", ""),
                            explanation=disc.get("explanation", ""),
                            metric=disc.get("metric", ""),
                            support=disc.get("support", ""),
                        ))
            
            result["execution"] = ExecutionSection(
                execution_paths=int(exec_data.get("execution_paths", 0)),
                reachable_units=int(exec_data.get("reachable_units", 0)),
                depth=int(exec_data.get("depth", 0)),
                narrative=str(exec_data.get("narrative", ""))[:500],
                highlights=tuple(highlights),
            )
        
        # Parse operational section
        if "operational" in result:
            op_data = result["operational"]
            if not isinstance(op_data, dict):
                raise ValueError("Field 'operational' must be a dict")
            
            result["operational"] = OperationalSection(
                api_count=int(op_data.get("api_count", 0)),
                data_count=int(op_data.get("data_count", 0)),
                event_count=int(op_data.get("event_count", 0)),
                dependency_count=int(op_data.get("dependency_count", 0)),
                narrative=str(op_data.get("narrative", ""))[:500],
            )
        
        # Parse validation section
        if "validation" in result:
            val_data = result["validation"]
            if not isinstance(val_data, dict):
                raise ValueError("Field 'validation' must be a dict")
            
            result["validation"] = ValidationSection(
                summary=str(val_data.get("summary", ""))[:500],
            )
        
        # Parse evidence list
        if "evidence" in result:
            evidence = result["evidence"]
            if not isinstance(evidence, list):
                raise ValueError("Field 'evidence' must be a list")
            # Limit and sanitize
            result["evidence"] = tuple(str(e) for e in evidence[:self.MAX_EVIDENCE_ITEMS])
        
        return result
    
    def create_fallback_comment(self, error: Exception) -> GithubComment:
        """
        Create a fallback GithubComment when parsing fails.
        
        Args:
            error: The error that caused the fallback
            
        Returns:
            Minimal valid GithubComment with error information
        """
        return GithubComment(
            executive_summary="Analysis completed. LLM comment generation encountered an issue.",
            review_priority="Review recommended - see compiler evidence below",
            biggest_surprise="Unable to generate surprise analysis",
            execution_summary="Execution analysis completed - see evidence for details",
            operational_summary="Operational analysis completed - see evidence for details",
            validation_summary="Validation analysis completed - see evidence for details",
            attention=f"Note: LLM-enhanced comment generation failed: {type(error).__name__}. Showing deterministic compiler output.",
            evidence=(
                "Factor compiler analysis completed successfully",
                "LLM comment enhancement encountered an issue",
                "All findings are based on deterministic compiler evidence",
            ),
        )