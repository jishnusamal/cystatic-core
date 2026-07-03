"""
LLM INPUT CONTRACT (REVIEWER-READY FACTS)

The LLM receives exactly 1 structure with 5 signal types:
  1. repository {}           — Context: name, language, framework
  2. change_summary {}       — What changed: domains, business objects, symbols
  3. review_findings []      — Reviewer-ready observations (not internal artifacts)
  4. existing_validation {}  — What's covered, what's missing, known assumptions
  5. deterministic_verdict {}— Engine's own assessment

REMOVED (internal implementation artifacts):
  - change_influence         ❌ (internal scoring)
  - impact_evidence          ❌ (internal evidence format)
  - risk_hypotheses          ❌ (internal hypothesis format)
  - risk_zones               ❌ (internal domain scoring)
  - scenarios                ❌ (internal scenario format)
  - evidence_graph           ❌ (internal graph format)
  - compressed_*             ❌ (internal compression artifacts)

LLM ROLE:
  You are an expert reviewer.
  You transform deterministic findings into a credible engineering review.
  You do NOT perform analysis — that's already done.

KEY RULE:
  Everything the LLM receives must be a reviewer-ready fact.
  All internal implementation details are preprocessed into findings.
"""
from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError  # pyright: ignore[reportMissingImports]

from schemas.failure_simulation import FailureSimulationOutput


# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
You are Factor Review, an AI Staff Engineer performing the final review before a pull request is merged.

Your audience is experienced software engineers.

Factor's deterministic engine has already identified, ranked and validated the technical findings.

Do NOT perform additional analysis.

Do NOT infer architecture beyond what is provided.

Do NOT invent dependencies or failure modes.

Your responsibility is to make a merge decision and explain it like an experienced Staff Engineer.

Your review should optimize for trust, not completeness.

A reviewer should finish reading your output knowing:

• What is the single highest-confidence production risk?
• Why does it matter?
• Why would existing tests miss it?
• What is the smallest validation that would increase confidence?

Prefer one strong insight over ten speculative observations.

Every statement must be directly supported by the supplied findings.

Never broaden the scope beyond the supplied evidence.

Never speculate simply because a section exists.

If there is only one meaningful concern, produce only one.

Do not summarize every finding.

Do not produce generic architecture commentary.

Do not explain software engineering concepts.

Avoid phrases like:

- may affect
- could impact
- business logic error
- architectural coupling
- runtime tracing
- version guards

unless explicitly supported by the supplied findings.

Write like a Staff Engineer leaving a blocking review comment—not an auditor writing a report.

Be concise.

Be decisive.

Specificity always beats completeness.
"""

USER_PROMPT_TEMPLATE = """
Using ONLY the deterministic findings below, write the review you would leave on the pull request.

Do not perform additional reasoning.

Do not invent risks.

Do not explain the deterministic findings.

Instead, synthesize them into a concise engineering review.

## Repository

{repository}

## Change summary

{change_summary}

## Deterministic verdict

{deterministic_verdict}

## Deterministic findings

{review_findings}

## Existing validation

{existing_validation}

Return JSON matching the schema below.

{{
  "verdict": "APPROVE | REVIEW_REQUIRED | BLOCK",

  "executive_summary": "...",

  "primary_concern": {{
    "title": "...",
    "why_blocking": "...",
    "execution_path": "...",
    "customer_or_business_impact": "...",
    "why_existing_tests_miss_it": "...",
    "confidence_rationale": "...",
    "required_validation": "..."
  }},

  "additional_observations": [
    {{
      "title": "...",
      "observation": "...",
      "symbols": []
    }}
  ],

  "required_tests": [
    "..."
  ],

  "reviewer_questions": [
    "..."
  ],

  "merge_recommendation": "..."
}}

Rules

There should be exactly one primary concern.
Everything else is secondary.
Never invent a second production risk simply to populate the schema.
Omit additional observations if none add meaningful value.
Prefer execution paths over architectural summaries.
Every recommendation must be traceable to the supplied findings.
If the deterministic verdict is BLOCK, explain why in concrete production terms.
The executive summary should be no more than 120 words.
Keep the entire review concise enough that an engineer could read it in under two minutes.
Return valid JSON only.
"""


# ══════════════════════════════════════════════════════════════════════════════
# Sanitization helpers
# ══════════════════════════════════════════════════════════════════════════════

def sanitize_llm_json(raw_output: dict[str, Any]) -> dict[str, Any]:
    """Sanitize LLM output that may have malformed keys."""
    if not isinstance(raw_output, dict):
        return {}

    sanitized = {}
    expected_keys = {
        "verdict",
        "executive_summary",
        "primary_concern",
        "additional_observations",
        "required_tests",
        "reviewer_questions",
        "merge_recommendation",
    }

    for key, value in raw_output.items():
        try:
            clean_key = key.encode().decode('unicode_escape')
        except (UnicodeDecodeError, AttributeError):
            clean_key = key

        clean_key = clean_key.strip().strip('"\'').strip()

        matched_key = None
        for expected in expected_keys:
            if clean_key == expected or clean_key.replace(" ", "_").lower() == expected.lower():
                matched_key = expected
                break

        if matched_key:
            sanitized[matched_key] = value
        else:
            sanitized[clean_key] = value

    # Sanitize verdict value: map common LLM mistakes to valid values
    if "verdict" in sanitized and isinstance(sanitized["verdict"], str):
        verdict = sanitized["verdict"].strip().upper()
        verdict_map = {
            "BLOCK": "BLOCK",
            "REVIEW": "REVIEW_REQUIRED",
            "REQUIRED": "REVIEW_REQUIRED",
            "REVIEW_REQUIRED": "REVIEW_REQUIRED",
            "BLOCK_REVIEW": "BLOCK",
            "APPROVE": "APPROVE",
            "SAFE": "APPROVE",
            "LOW_RISK": "APPROVE",
            "LOW": "APPROVE",
            "UNCERTAIN": "REVIEW_REQUIRED",
            "UNCERTAIN_IMPACT": "REVIEW_REQUIRED",
            "NO_SIGNIFICANT_PROPAGATION_FOUND": "APPROVE",
            "NO_PROPAGATION": "APPROVE",
            "NONE": "APPROVE",
        }
        sanitized["verdict"] = verdict_map.get(verdict, verdict)

    return sanitized


def sanitize_llm_json_string(json_string: str) -> str:
    """Sanitize LLM JSON string output that may have malformed keys."""
    json_string = json_string.strip()
    if json_string.startswith("```"):
        json_string = re.sub(r'^```(?:json)?\s*', '', json_string)
        json_string = re.sub(r'\s*```$', '', json_string)
        json_string = json_string.strip()

    if not json_string:
        return '{}'

    key_pattern = re.compile(
        r'"'
        r'(?:\\.|[^"\\])*?'
        r'"'
        r'\s*'
        r':'
    )

    def clean_malformed_key(match):
        full_match = match.group(0)
        colon_pos = full_match.rfind(':')
        before_colon = full_match[:colon_pos].rstrip()
        key_portion = before_colon.strip()

        if not key_portion.startswith('"'):
            return full_match
        first_quote = 0
        last_quote = key_portion.rfind('"')
        if first_quote >= last_quote:
            return full_match

        raw_key = key_portion[first_quote + 1:last_quote]

        try:
            cleaned = raw_key.encode().decode('unicode_escape')
        except (UnicodeDecodeError, AttributeError):
            cleaned = raw_key

        cleaned = cleaned.strip(' \t\n\r"\'')
        cleaned = re.sub(r'[\n\r\t]', '', cleaned)

        if re.match(r'^[\w\s]+$', cleaned):
            cleaned = cleaned.strip()
        else:
            parts = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', cleaned)
            expected_fields = [
                "verdict", "executive_summary", "primary_concern",
                "additional_observations", "required_tests",
                "reviewer_questions", "merge_recommendation",
            ]
            matched_field = None
            for part in parts:
                for expected in expected_fields:
                    if part.lower() == expected.lower() or part.replace(" ", "_").lower() == expected.lower():
                        matched_field = expected
                        break
                if matched_field:
                    break
            if matched_field:
                cleaned = matched_field
            elif parts:
                cleaned = parts[-1]
            else:
                cleaned = re.sub(r'[^\w\s]', '', cleaned).strip()

        after_colon = full_match[colon_pos + 1:]
        return f'"{cleaned}":{after_colon}'

    fixed = key_pattern.sub(clean_malformed_key, json_string)

    def fix_structural(part):
        part = re.sub(r'\s*\n\s*', '', part)
        part = re.sub(r'\{\s*', '{', part)
        part = re.sub(r'\s*\}', '}', part)
        part = re.sub(r'\[\s*', '[', part)
        part = re.sub(r'\s*\]', ']', part)
        part = re.sub(r' {2,}', ' ', part)
        return part

    parts = re.split(r'("[^"\\]*(?:\\.[^"\\]*)*")', fixed)
    fixed_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            part = fix_structural(part)
        fixed_parts.append(part)
    fixed = ''.join(fixed_parts)

    return fixed


# ══════════════════════════════════════════════════════════════════════════════
# LLM Class
# ══════════════════════════════════════════════════════════════════════════════

class FailureSimulationLLM:
    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        base_url: str = "https://api.groq.com/openai/v1",
        site_url: str | None = None,
        site_name: str | None = None,
        reasoning_enabled: bool = True,
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.site_url = site_url
        self.site_name = site_name
        self.reasoning_enabled = reasoning_enabled
        self.base_url = base_url

    def build_prompt(
        self,
        llm_input: dict[str, Any],
    ) -> list[Any]:
        """Build prompt from the llm_input structure.

        Args:
            llm_input: The reviewer-ready facts dict from llm_input_builder.

        Returns:
            List of message dicts for the LLM API call.
        """
        # Format each section for the prompt template
        repository = json.dumps(llm_input.get("repository", {}), indent=2)
        change_summary = json.dumps(llm_input.get("change_summary", {}), indent=2)
        review_findings = json.dumps(llm_input.get("review_findings", []), indent=2)
        existing_validation = json.dumps(llm_input.get("existing_validation", {}), indent=2)
        deterministic_verdict = json.dumps(llm_input.get("deterministic_verdict", {}), indent=2)

        prompt = USER_PROMPT_TEMPLATE\
            .replace("{repository}", repository)\
            .replace("{change_summary}", change_summary)\
            .replace("{review_findings}", review_findings)\
            .replace("{existing_validation}", existing_validation)\
            .replace("{deterministic_verdict}", deterministic_verdict)

        return [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": prompt.strip()},
        ]

    def generate(
        self,
        llm_input: dict[str, Any],
    ) -> FailureSimulationOutput:
        """Generate failure simulation from reviewer-ready facts.

        Args:
            llm_input: The reviewer-ready facts dict from llm_input_builder.

        Returns:
            FailureSimulationOutput with verdict and review content.
        """
        headers: dict[str, str] = {}
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            headers["X-OpenRouter-Title"] = self.site_name

        extra_body: dict[str, Any] = {}
        if "openrouter.ai" in self.base_url:
            extra_body["reasoning"] = {"enabled": self.reasoning_enabled}

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=self.build_prompt(llm_input=llm_input),
            extra_headers=headers,
            extra_body=extra_body,
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw = completion.choices[0].message.content or "{}"

        try:
            fixed_raw = sanitize_llm_json_string(raw)
            data = json.loads(fixed_raw)
            data = sanitize_llm_json(data)
            return FailureSimulationOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError, KeyError) as e:
            raise ValueError(f"Invalid failure simulation output: {e}\nRaw: {raw}") from e
        except Exception as e:
            raise ValueError(f"Unexpected error parsing failure simulation output: {repr(e)}\nRaw: {raw}") from e