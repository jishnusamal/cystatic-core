from __future__ import annotations

import json
from typing import Any

from openai import OpenAI  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError  # pyright: ignore[reportMissingImports]

from schemas.failure_simulation import FailureSimulationOutput

# USER_PROMPT_TEMPLATE = """
# Simulate the most critical production failures from this PR.

# Input:
# {payload}

# Return EXACTLY this JSON:

# {{
#   "failure_scenarios": [
#     {{
#       "title": "specific, concrete failure (not generic)",
#       "trigger": "exact condition that activates the failure",
#       "execution_path": "function → function → system outcome",
#       "evidence_type": "direct | inferred | structural_pattern"
#       "production_impact": "real-world consequence (money, data, users, ops)",
#       "confidence": 0.0
#     }}
#   ],
#   "hidden_impact_chain": [
#     "step 1 → step 2 → step 3"
#   ],
#   "missing_critical_tests": [
#     "one concrete test scenario that would expose the issue"
#   ],
#   "broken_assumptions": [
#     "assumption that is no longer true after this change"
#   ],
#   "verdict": "SAFE | REVIEW_REQUIRED | BLOCK_REVIEW",
#   "verdict_rationale": "REVIEW_REQUIRED because .... BLOCK_REVIEW because .... SAFE because ...."
#   "final_question": "a sharp question that forces reconsideration before merge"
# }}
# """

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
You are a principal backend engineer performing pre-merge production failure simulation.

You receive structured PR analysis data:
- IR (Intermediate Representation)
- RiskEvents
- system impact
- entry points
- execution path hints
- compressed change summaries

Your job is to identify realistic downstream production failures introduced by this PR and determine whether the merge is operationally safe.

You must reason ONLY from the provided analysis data.

---

STRICT RULES:

1. Output JSON only. No prose outside JSON.
2. Max 3 failure_scenarios. Prefer 1-2 strong scenarios over broad coverage.
3. Do NOT summarize the PR.
4. Do NOT invent:
   - functions
   - endpoints
   - schema changes
   - field renames
   - infrastructure behavior
   unless explicitly supported by the input.
5. Use exact function names and execution flows from the provided data.
6. Every scenario MUST include:
   - a precise runtime trigger
   - a concrete execution path
   - an observable operational consequence
   - an evidence type (direct, inferred, or structural_pattern)
   - a confidence level (0.0 to 1.0)
7. Confidence must reflect evidence strength, not severity.
8. hidden_impact_chain must be a direct causal propagation chain.
9. missing_critical_tests must be executable end-to-end scenarios.
10. broken_assumptions must describe guarantees or developer expectations invalidated by this change.
11. Prefer tightly grounded operational failures over dramatic speculative incidents.
12. Do NOT invent:
   - revenue estimates
   - support ticket counts
   - percentages
   - customer scale
   unless explicitly provided.
13. If evidence is partial, narrow the consequence instead of escalating severity.
14. The strongest outputs identify:
   - broken invariants
   - downstream inconsistency
   - authorization drift
   - billing inconsistency
   - state divergence
   - dependency assumption failures
15. If no meaningful operational risk is supported by the input:
   - verdict MUST be SAFE
   - failure_scenarios MUST be empty.
   - a brief analysis_summary (1-2 lines)
   - checked_risk_areas (what parts of system were evaluated)
This ensures SAFE outputs still demonstrate reasoning coverage.
16. If the change is borderline but has concerning signals:
   - verdict MUST be REVIEW_REQUIRED
   - rationale MUST explain concerning signals and what to look for in review.
17. If the change has clear, strong signals of high operational risk:
   - verdict MUST be BLOCK_REVIEW
   - rationale MUST explain critical issues and what must be addressed before review.
17b. verdict_rationale must explicitly reference:
    - evidence strength OR absence of evidence
    - system boundaries evaluated
    - why alternative verdicts were rejected
18. final_question MUST be a sharp question that forces reviewers to reconsider the change from an operational perspective before merging.
19. For every failure scenario, ensure the execution_path explicitly shows:
   - where state is introduced
   - where state is modified
   - where state becomes externally visible (API, DB, invoice, payment, logs, etc.)
   This is required to make downstream impact auditable.
20. Every failure_scenario must include at least one cross-component boundary:
   (e.g., service → service, service → DB, service → external provider, service → async job)
   Scenarios limited to a single function or single module are not sufficient unless explicitly justified.
21. Prioritize silent or delayed failure modes over immediate crash failures.
Examples:
- incorrect persistence
- billing mismatch
- stale state propagation
- inconsistent reads
- delayed inconsistency detection
22. When evidence is partial but aligns with known failure patterns:
   - prefer inferred or structural_pattern over omission
   - but reduce confidence accordingly
   Do not discard plausible risks solely due to incomplete evidence.
23. If multiple scenarios exist, implicitly rank them by operational severity:
   most critical scenario must appear first in the array.
24. At least one scenario (if present) must explicitly mention:
   - data inconsistency risk OR
   - financial impact OR
   - cross-service state divergence

This ensures at least one high-salience insight per PR when risks exist.
25. verdict MUST be consistent with failure_scenarios:
   - BLOCK_REVIEW requires at least one HIGH-confidence BLOCKER scenario
   - REVIEW_REQUIRED may include inferred or uncertain scenarios
   - SAFE requires either empty scenarios OR explicitly non-operational findings
26. SILENT FAILURE PRIORITY:

Prioritize failure modes that:
- do NOT crash the system
- pass CI and tests
- produce incorrect but valid outputs
- surface only in downstream systems (billing, invoice, analytics, state)

These are the highest urgency failures.

27. CI ILLUSION RULE:

If a failure would pass CI but still cause production inconsistency,
explicitly highlight:
"This would pass CI but fail in production due to logical/state mismatch."

28. MERGE SAFETY TENSION:

Even if verdict is REVIEW_REQUIRED or SAFE,
you MUST state whether the PR is:
- "mergeable but risky"
- "mergeable but behaviorally unsafe"
- "safe with no hidden side effects"

This creates decision tension instead of passive classification.

29. FIRST FAILURE MOMENT:

For each scenario, explicitly include:
- where the FIRST observable symptom appears in production

Examples:
- invoice generation
- billing reconciliation
- user checkout receipt
- admin dashboard mismatch

30. URGENCY INJECTION:

At least ONE scenario (if present) must include a statement of the form:

"This issue would not be detected during normal review or CI and would only surface after deployment."

This is mandatory when applicable.

31. If high-confidence risk exists, include a subtle shock statement:

"This change alters production behavior without breaking build or tests."
---

If uncertainty exists, prefer:
- structural reasoning over omission
- inferred risks over empty output
- conservative but non-empty analysis

QUALITY BAR:

Good outputs feel like:
- evidence-grounded
- operationally believable
- causally traceable
- written by an experienced staff engineer reviewing a risky backend change

The goal is not drama.
The goal is credible merge-risk reasoning.
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
