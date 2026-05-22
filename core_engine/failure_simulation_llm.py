from __future__ import annotations

import json
from typing import Any

from openai import OpenAI  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError  # pyright: ignore[reportMissingImports]

from schemas.failure_simulation import FailureSimulationOutput


USER_PROMPT_TEMPLATE = """
Simulate the most critical production failures from this PR.

Input:
{payload}

Return EXACTLY this JSON:

{{
  "failure_scenarios": [
    {{
      "title": "specific, concrete failure (not generic)",
      "trigger": "exact condition that activates the failure",
      "execution_path": "function → function → system outcome",
      "evidence_type": "direct | inferred | structural_pattern",
      "production_impact": "real-world consequence (money, data, users, ops)",
      "confidence": 0.0,

      "first_observable_signal": "where the issue is first detected in production (dashboard, invoice, logs, alerts)",
      "silent_failure": true,
      "ci_would_catch": false,
      "false_confidence_reason": "Why this change looks safe at first glance even though it isn't.",
      "why_it_slips_through": "Why CI, reviews, or normal testing fail to catch the issue.",
      "merge_confidence_trap": "The psychological reason a reviewer will wrongly approve the PR despite risk.",
      "merge_risk_level": "LOW | MEDIUM | HIGH | CRITICAL"
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

  "verdict": "SAFE | REVIEW_REQUIRED | BLOCK_REVIEW",

  "verdict_rationale": "REVIEW_REQUIRED because .... BLOCK_REVIEW because .... SAFE because ....",

  "final_question": "a sharp question that forces reconsideration before merge"
}}
"""

SYSTEM_PROMPT = """
You operate under a production uncertainty reasoning contract.

This system is not a bug finder. It is a confidence-break simulation engine.

---

# 🧠 REASONING CONTRACT (CRITICAL)

You must follow this thinking process internally before producing output:

1. Assume the PR is locally correct and passes all tests.
   (This is the "false safety baseline")

2. Identify only failures that emerge from system interaction, not local code mistakes.

3. Prefer failures where:
   - system behavior diverges from code intent
   - state becomes inconsistent across boundaries
   - correctness exists locally but breaks globally

4. If full detail is missing, you MUST:
   - generalize safely
   - reason at system level (service, DB, external systems)
   - avoid stalling or refusing generation

5. Your goal is NOT completeness.
   Your goal is:
   → identifying the most likely “this looked safe but wasn’t” failure

---

# ⚡ AHA MOMENT PRIORITY RULE

At least one scenario (if possible) MUST maximize:

- surprise under normal engineering review
- hidden cross-system dependency
- incorrect confidence under CI-green assumption

BUT:
This is a soft optimization goal, not a strict requirement.

---

# 🚨 OUTPUT STABILITY RULE

If strict constraints conflict with available information:

- prefer abstraction over omission
- prefer general system reasoning over function-level precision
- ALWAYS return valid JSON
- NEVER return empty output

---

# 🧭 OUTPUT INTENT

You are simulating:

> “What would a competent engineer confidently merge that later breaks production?”

NOT:

- listing all possible bugs
- proving correctness
- exhaustive system analysis
"""

class FailureSimulationLLM:
    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-120b",
        # base_url: str = "https://api.cerebras.ai/v1",
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

    def build_prompt(self, compressed_ir: dict[str, Any]) -> list[Any]:
        payload = json.dumps(compressed_ir, indent=2)
        return [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(payload=payload).strip(),
            },
        ]

    def generate(self, compressed_ir: dict[str, Any]) -> FailureSimulationOutput:
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
            messages=self.build_prompt(compressed_ir),
            extra_headers=headers,
            extra_body=extra_body,
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw = completion.choices[0].message.content or "{}"

        try:
            data = json.loads(raw)
            return FailureSimulationOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            raise ValueError(f"Invalid failure simulation output: {e}\nRaw: {raw}") from e
