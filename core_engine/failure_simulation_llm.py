from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError  # pyright: ignore[reportMissingImports]

from schemas.failure_simulation import FailureSimulationOutput


USER_PROMPT_TEMPLATE = """
Simulate production failures from this PR analysis.

The system has already constructed:
1. A **causal graph** showing how changed symbols connect to downstream systems
2. A **propagation impact tree** showing blast radius with confidence scores
3. **Matched failure templates** suggesting specific failure classes
4. **System behavior deltas** describing semantic shifts (not just code diffs)
5. **Risk patterns** detected from code analysis
6. **Causal hypotheses** — structured, scored inferences about what breaks

Your job: synthesize these into ranked failure scenarios.

CAUSAL GRAPH:
{causal_graph}

IMPACT TREE (blast radius):
{impact_tree}

FAILURE TEMPLATE MATCHES:
{failure_template_matches}

SYSTEM BEHAVIOR DELTAS:
{system_behavior_deltas}

RISK PATTERNS:
{risk_patterns}

CHANGE GRAPH:
{change_graph}

BEHAVIOR DIFF:
{behavior_diff}

CAUSAL HYPOTHESES (structured inferences attached to causal edges):
{causal_hypotheses}

Each causal hypothesis includes:
- from/to symbols and edge type
- the hypothesis text
- a confidence score (0.0–1.0) reflecting how strongly the inference is supported
- a failure class prediction (e.g. null_propagation, stale_cache, auth_bypass_chain)
- the propagation path it follows

Use these as your starting point for failure scenario construction. Each hypothesis is a potential failure mode — validate it against the causal graph and impact tree, then promote to a full scenario if supported.

Return JSON with scored, concrete failure scenarios.

{
  "verdict": "SAFE | LOW_RISK | UNCERTAIN_IMPACT | NO_SIGNIFICANT_PROPAGATION_FOUND | REVIEW_REQUIRED | BLOCK_REVIEW",

  "failure_scenarios": [
    {{
      "title": "specific, concrete failure (not generic)",
      "trigger": "exact condition that activates the failure",
      "execution_path": "function → function → system outcome",
      "evidence_type": "direct | inferred | structural_pattern",
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
}
"""

SYSTEM_PROMPT = """
You are Factor's Production Failure Simulator.

Your job is to help engineers understand:
> "How could this PR break production even if CI passes?"

You operate on EXPLICITLY MODELED system structure:
- A causal graph showing how changes propagate
- An impact tree with confidence propagation
- Pre-matched failure templates
- System behavior deltas (semantic shifts, not just code diffs)

---

# REASONING STYLE

You are NOT a validator. You are a simulation engine.

You should behave like a senior engineer running a production walkthrough
using the explicit system model provided to you.

---

# HOW TO THINK

You may:
- Use the causal graph to trace failure propagation paths
- Use the impact tree to determine blast radius
- Use failure templates as structured hypotheses (not guesses)
- Assign hop_confidence that decays with causal distance
- Rank scenarios by confidence * severity

You should NOT:
- Invent symbols or systems not in the causal graph
- Ignore the failure templates — they are grounded signals
- Claim absolute certainty (confidence must be calibrated)
- Default to SAFE — SAFE requires positive evidence

---

# VERDICT GUIDELINES

SAFE: Evidence confirms no production impact. Zero failure scenarios. STRONG rationale required.
LOW_RISK: Minor concerns, no critical system impact. Some risk but acceptable.
UNCERTAIN_IMPACT: Suspicious patterns found but no direct evidence of failure chain.
NO_SIGNIFICANT_PROPAGATION_FOUND: Changes exist but causal propagation shows no downstream impact.
REVIEW_REQUIRED: One or more concrete failure scenarios with confidence >= 0.6.
BLOCK_REVIEW: Critical failure scenario(s) with high confidence and severe impact.

---

# OUTPUT PRINCIPLES

Be practical, not academic.
Prefer 1-3 strong scenarios over many weak ones.
Use the causal chain field to show your propagation reasoning.
Use failure_class to categorize the type of failure.
"""


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
        compressed_ir: dict[str, Any],
        causal_graph: dict[str, Any] | None = None,
        impact_tree: dict[str, Any] | None = None,
        failure_template_matches: list[dict] | None = None,
        system_behavior_deltas: list[dict] | None = None,
    ) -> list[Any]:
        """Build prompt with causal graph, impact tree, and failure templates."""
        # Extract IR components — causal_hypotheses replaces old unknowns bucket
        core_context = compressed_ir.get("core_context", {})
        change_graph = compressed_ir.get("change_graph", [])
        behavior_diff = compressed_ir.get("behavior_diff", [])
        causal_hypotheses = compressed_ir.get("causal_hypotheses", [])
        risk_events = compressed_ir.get("risk_events", [])

        # Format causal graph
        causal_graph_str = json.dumps(causal_graph or {}, indent=2)

        # Format impact tree
        impact_tree_str = json.dumps(impact_tree or {}, indent=2)

        # Format failure template matches
        templates_str = json.dumps(failure_template_matches or [], indent=2)

        # Format system behavior deltas
        deltas_str = json.dumps(system_behavior_deltas or [], indent=2)

        # Format risk patterns
        risk_patterns_str = json.dumps(risk_events, indent=2)

        # Format change graph
        change_graph_str = json.dumps(change_graph, indent=2)

        # Format behavior diff
        behavior_diff_str = json.dumps(behavior_diff, indent=2)

        # Format causal hypotheses (structured, scored, edge-attached)
        causal_hypotheses_str = json.dumps(causal_hypotheses, indent=2)

        prompt = USER_PROMPT_TEMPLATE\
            .replace("{causal_graph}", causal_graph_str)\
            .replace("{impact_tree}", impact_tree_str)\
            .replace("{failure_template_matches}", templates_str)\
            .replace("{system_behavior_deltas}", deltas_str)\
            .replace("{risk_patterns}", risk_patterns_str)\
            .replace("{change_graph}", change_graph_str)\
            .replace("{behavior_diff}", behavior_diff_str)\
            .replace("{causal_hypotheses}", causal_hypotheses_str)

        return [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": prompt.strip()},
        ]

    def generate(
        self,
        compressed_ir: dict[str, Any],
        causal_graph: dict[str, Any] | None = None,
        impact_tree: dict[str, Any] | None = None,
        failure_template_matches: list[dict] | None = None,
        system_behavior_deltas: list[dict] | None = None,
    ) -> FailureSimulationOutput:
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
                compressed_ir=compressed_ir,
                causal_graph=causal_graph,
                impact_tree=impact_tree,
                failure_template_matches=failure_template_matches,
                system_behavior_deltas=system_behavior_deltas,
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