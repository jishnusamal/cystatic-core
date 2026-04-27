from __future__ import annotations

import json
from typing import Any

from openai import OpenAI  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError  # pyright: ignore[reportMissingImports]

from schemas.failure_simulation import FailureSimulationOutput


SYSTEM_PROMPT = """
You are a senior backend engineer performing pre-merge production failure simulation.

You receive structured PR analysis data:
- IR (Intermediate Representation)
- RiskEvents
- system impact
- entry points
- execution path hints
- compressed change summaries

Your job is NOT to analyze.

Your job is to identify concrete production failures and force a merge decision.

You must simulate real incidents using ONLY the provided data.

---

STRICT RULES:

1. Output JSON only. No prose outside JSON.
2. Max 3 failure_scenarios. Prefer 1-2 high-quality scenarios over 3 weak ones.
3. Do NOT summarize the PR.
4. Do NOT invent missing functions, endpoints, or logic.
5. Use exact function names and flows provided.
6. Every scenario MUST include:
   - a precise trigger (not vague change)
   - a concrete execution path (function → function → outcome)
   - a real production impact (money, data, users, ops)
   - confidence BETWEEN 0.6 and 0.95
7. NEVER use confidence = 0.0.
8. Avoid generic language:
   - forbidden: "may break", "could cause", "logic changed"
   - required: assertive, concrete statements
9. hidden_impact_chain must be a step-by-step causal chain.
10. missing_critical_tests must be executable test scenarios (not function names).
11. broken_assumptions must describe developer beliefs that are now invalid.
12. If no real failure exists → verdict MUST be SAFE and failure_scenarios must be empty.

---

QUALITY BAR:

Each failure must feel like a real incident:
- specific trigger
- traceable execution path
- irreversible or costly impact

If the output does not make a senior engineer hesitate before merging, it is wrong.
"""


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
      "production_impact": "real-world consequence (money, data, users, ops)",
      "confidence": 0.0
    }}
  ],
  "hidden_impact_chain": [
    "step 1 → step 2 → step 3"
  ],
  "missing_critical_tests": [
    "one concrete test scenario that would expose the issue"
  ],
  "broken_assumptions": [
    "assumption that is no longer true after this change"
  ],
  "verdict": "SAFE | REVIEW_REQUIRED | BLOCK_REVIEW",
  "final_question": "a sharp question that forces reconsideration before merge"
}}
"""


class FailureSimulationLLM:
    def __init__(
        self,
        api_key: str,
        model: str = "qwen-3-235b-a22b-instruct-2507",
        base_url: str = "https://api.cerebras.ai/v1",
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

    def build_prompt(self, compressed_ir: dict[str, Any]) -> list[dict[str, str]]:
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
