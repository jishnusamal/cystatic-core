"""
PHASE 5 — LLM INPUT CONTRACT (FACTOR V5 — MINIMAL CAUSAL TRUTH)

The LLM receives exactly 1 structure with 4 signal types:
  1. change_influence []       — ONLY scored symbols + domains (Layer 1)
  2. execution_paths []        — Hard truth propagation chains (Layer 2+3)
  3. soft_edges []             — Weak adjacency only if needed (Layer 2)
  4. constraints {}            — System rules (what is allowed/forbidden)
  5. risk_zones []             — Domain regions (checkout, invoice, tax, etc.)
  6. changed_symbols []        — Tiny hint: list of changed symbols

REMOVED (not reasoning inputs):
  - files (enriched_files)     ❌ (too big + already abstracted elsewhere)
  - excluded_files             ❌ (irrelevant to reasoning)
  - keywords_detected          ❌ (already in change_influence)
  - risk_patterns              ❌ (already encoded in domain + influence)
  - entry_points_affected      ❌ (already in execution_paths)
  - system_impact              ❌ (already in propagation layer)
  - pr_risk_score              ❌ (system opinion, LLM should derive)
  - pr_risk_level              ❌ (system opinion, LLM should derive)
  - compressed_for_llm         ❌ (reintroduces everything we separated)
  - failure_simulation         ❌ (this is OUTPUT, not INPUT)

LLM ROLE:
  You are a causal reasoning engine.
  You derive failure scenarios from nodes, edges, and constraints only.

KEY RULE:
  Everything the LLM receives must be a node, edge, or constraint.
  All other data is preprocessing junk that causes:
  - contradiction
  - overconfidence noise
  - hallucinated reconciliation
  - diluted signal strength
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

USER_PROMPT_TEMPLATE = """
You are a causal reasoning engine analyzing production risk in a codebase.

You receive ONLY nodes, edges, and constraints. Everything else is noise.

RULES:

1. Every failure scenario MUST originate from execution_paths or soft_edges.
2. You may NOT create new chains or new flows.
3. You may only use:
   - change_influence (what changed + where it matters)
   - execution_paths (hard truth propagation)
   - soft_edges (weak adjacency, only if execution_paths are sparse)
   - constraints (system rules: what is allowed/forbidden)
   - risk_zones (domain regions: checkout, invoice, tax, etc.)
   - changed_symbols (list of modified symbols)

4. IMPORTANT PRIORITY ORDER:
   execution_paths > soft_edges > change_influence > constraints > risk_zones

5. change_influence tells you WHAT changed and HOW MUCH it matters.
   It does NOT create risk by itself.

6. execution_paths are the TRUTH — ordered propagation chains.
   If a path exists, risk can flow through it.

7. soft_edges are WEAK signals — use only when execution_paths are sparse.
   They suggest likely propagation but are not guaranteed.

8. constraints define SYSTEM RULES — idempotency, transactions, retries, etc.
   Violating a constraint is a strong failure signal.

9. risk_zones tell you WHERE it matters — checkout, invoice, tax, etc.

10. If no execution_path has changed symbols AND no soft_edge connects to changed symbols:
    return NO_SIGNIFICANT_PROPAGATION_FOUND

11. SAFE is ONLY allowed if:
    - no execution path touches changed symbols
    - no soft edge connects to changed symbols

12. NEVER default to SAFE.

13. Prefer 1–3 high-confidence failures over none.

────────────────────────────────────────────────────────────────────────────────
# INPUT STRUCTURE
────────────────────────────────────────────────────────────────────────────────

{input_structure}

────────────────────────────────────────────────────────────────────────────────
# OUTPUT FORMAT
────────────────────────────────────────────────────────────────────────────────

Return STRICT JSON only:

{{
  "verdict": "SAFE | LOW_RISK | UNCERTAIN_IMPACT | NO_SIGNIFICANT_PROPAGATION_FOUND | REVIEW_REQUIRED | BLOCK_REVIEW",

  "failure_scenarios": [
    {{
      "title": "specific, concrete failure (not generic)",
      "trigger": "exact condition that activates the failure",
      "execution_path": "function → function → system outcome",
      "evidence_type": "direct | inferred | structural_pattern | inferred_bridge",
      "production_impact": "real-world consequence (money, data, users, ops)",
      "confidence": 0.0,
      "hop_confidence": 0.0,
      "causal_chain": "symbol → symbol → symbol (with confidence at each hop)",
      "failure_class": "idempotency_break | double_charge_double_write | null_propagation | stale_cache | partial_update_drift | silent_fallback_activation | auth_bypass_chain | tax_billing_mismatch | logic_negation_flip | data_validation_removed | async_event_mismatch | state_inconsistency | other",

      "first_observable_signal": "where the issue is first detected in production (dashboard, invoice, logs, alerts)",
      "silent_failure": true,
      "ci_would_catch": false,
      "false_confidence_reason": "Why this change looks safe at first glance even though it isn't.",
      "why_it_slips_through": "Why CI, reviews, or normal testing fail to catch the issue.",
      "merge_confidence_trap": "The psychological reason a reviewer will wrongly approve the PR despite risk.",
      "merge_risk_level": "LOW | MEDIUM | HIGH | CRITICAL",
      "supported_by": ["symbol1", "symbol2"],
      "reasoning": "Step-by-step reasoning linking evidence to failure"
    }}
  ],

  "hidden_impact_chain": [
    "step 1 → step 2 → step 3"
  ],

  "checked_risk_areas": [
    "areas of system analyzed (checkout, billing, invoice, auth, etc.)"
  ],

  "missing_critical_tests": [
    "one concrete test scenario that would expose the issue"
  ],

  "broken_assumptions": [
    "assumption that is no longer true after this change"
  ],

  "silent_failure_summary": "1-2 lines describing how this could pass CI but still fail in production",
  "merge_risk_statement": "This PR is mergeable but behaviorally unsafe under production conditions",
  "verdict_rationale": "SAFE because .... LOW_RISK because .... REVIEW_REQUIRED because .... BLOCK_REVIEW because ....",
  "final_question": "a sharp question that forces reconsideration before merge"
}}
"""

SYSTEM_PROMPT = """
You are a causal reasoning engine analyzing production risk in a codebase.

You receive ONLY nodes, edges, and constraints. Everything else is noise.

RULES:

1. Every failure scenario MUST originate from execution_paths or soft_edges.
2. You may NOT create new chains or new flows.
3. You may only use:
   - change_influence (what changed + where it matters)
   - execution_paths (hard truth propagation)
   - soft_edges (weak adjacency, only if execution_paths are sparse)
   - constraints (system rules: what is allowed/forbidden)
   - risk_zones (domain regions: checkout, invoice, tax, etc.)
   - changed_symbols (list of modified symbols)

4. IMPORTANT PRIORITY ORDER:
   execution_paths > soft_edges > change_influence > constraints > risk_zones

5. change_influence tells you WHAT changed and HOW MUCH it matters.
   It does NOT create risk by itself.

6. execution_paths are the TRUTH — ordered propagation chains.
   If a path exists, risk can flow through it.

7. soft_edges are WEAK signals — use only when execution_paths are sparse.
   They suggest likely propagation but are not guaranteed.

8. constraints define SYSTEM RULES — idempotency, transactions, retries, etc.
   Violating a constraint is a strong failure signal.

9. risk_zones tell you WHERE it matters — checkout, invoice, tax, etc.

10. If no execution_path has changed symbols AND no soft_edge connects to changed symbols:
    return NO_SIGNIFICANT_PROPAGATION_FOUND

11. SAFE is ONLY allowed if:
    - no execution path touches changed symbols
    - no soft edge connects to changed symbols

12. NEVER default to SAFE.

13. Prefer 1–3 high-confidence failures over none.

OUTPUT MUST BE STRICT JSON.
"""


# ══════════════════════════════════════════════════════════════════════════════
# Sanitization helpers (unchanged from V3)
# ══════════════════════════════════════════════════════════════════════════════

def sanitize_llm_json(raw_output: dict[str, Any]) -> dict[str, Any]:
    """Sanitize LLM output that may have malformed keys."""
    if not isinstance(raw_output, dict):
        return {}

    sanitized = {}
    expected_keys = {
        "failure_scenarios",
        "hidden_impact_chain",
        "checked_risk_areas",
        "missing_critical_tests",
        "broken_assumptions",
        "silent_failure_summary",
        "merge_risk_statement",
        "verdict_rationale",
        "verdict",
        "final_question",
        "system_behavior_deltas",
        "matched_failure_templates",
        "blast_radius",
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
                "failure_scenarios", "hidden_impact_chain", "checked_risk_areas",
                "missing_critical_tests", "broken_assumptions", "silent_failure_summary",
                "merge_risk_statement", "verdict_rationale", "verdict", "final_question",
                "system_behavior_deltas", "matched_failure_templates", "blast_radius",
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
        repo: str = "",
        pr_number: int = 0,
        change_influence: list[dict[str, Any]] | None = None,
        execution_paths: list[dict[str, Any]] | None = None,
        soft_edges: list[dict[str, Any]] | None = None,
        constraints: dict[str, Any] | None = None,
        risk_zones: list[str] | None = None,
        changed_symbols: list[str] | None = None,
    ) -> list[Any]:
        """Build prompt with the V5 minimal causal truth input contract.

        Args:
            repo: Repository identifier.
            pr_number: PR number.
            change_influence: Scored symbols + domains (Layer 1).
            execution_paths: Hard truth propagation chains (Layer 2+3).
            soft_edges: Weak adjacency edges (Layer 2, only if needed).
            constraints: System rules (what is allowed/forbidden).
            risk_zones: Domain regions (checkout, invoice, tax, etc.).
            changed_symbols: List of modified symbols.

        Returns:
            List of message dicts for the LLM API call.
        """
        input_structure = {
            "repo": repo,
            "pr_number": pr_number,
            "change_influence": change_influence or [],
            "execution_paths": execution_paths or [],
            "soft_edges": soft_edges or [],
            "constraints": constraints or {},
            "risk_zones": risk_zones or [],
            "changed_symbols": changed_symbols or [],
        }
        
        prompt = USER_PROMPT_TEMPLATE\
            .replace("{input_structure}", json.dumps(input_structure, indent=2))

        return [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": prompt.strip()},
        ]

    def generate(
        self,
        repo: str = "",
        pr_number: int = 0,
        change_influence: list[dict[str, Any]] | None = None,
        execution_paths: list[dict[str, Any]] | None = None,
        soft_edges: list[dict[str, Any]] | None = None,
        constraints: dict[str, Any] | None = None,
        risk_zones: list[str] | None = None,
        changed_symbols: list[str] | None = None,
    ) -> FailureSimulationOutput:
        """Generate failure simulation from V5 minimal causal truth input contract.

        Args:
            repo: Repository identifier.
            pr_number: PR number.
            change_influence: Scored symbols + domains (Layer 1).
            execution_paths: Hard truth propagation chains (Layer 2+3).
            soft_edges: Weak adjacency edges (Layer 2, only if needed).
            constraints: System rules (what is allowed/forbidden).
            risk_zones: Domain regions (checkout, invoice, tax, etc.).
            changed_symbols: List of modified symbols.

        Returns:
            FailureSimulationOutput with verdict and scenarios.
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
            messages=self.build_prompt(
                repo=repo,
                pr_number=pr_number,
                change_influence=change_influence,
                execution_paths=execution_paths,
                soft_edges=soft_edges,
                constraints=constraints,
                risk_zones=risk_zones,
                changed_symbols=changed_symbols,
            ),
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