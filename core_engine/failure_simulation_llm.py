"""
LLM INPUT CONTRACT (EVIDENCE-DRIVEN)

The LLM receives exactly 1 structure with 5 signal types:
  1. change_influence []       — ONLY scored symbols + domains (Layer 1)
  2. impact_evidence []        — Evidence connecting changed symbols (Layer 2)
  3. risk_zones []             — Domain regions (checkout, invoice, tax, etc.)
  4. changed_symbols []        — Tiny hint: list of changed symbols
  5. impact_propagation {}     — Optional: Impact Propagation Kernel output

REMOVED (not reasoning inputs):
  - files (enriched_files)     ❌ (too big + already abstracted elsewhere)
  - excluded_files             ❌ (irrelevant to reasoning)
  - keywords_detected          ❌ (already in change_influence)
  - risk_patterns              ❌ (already encoded in domain + influence)
  - entry_points_affected      ❌ (already in impact_evidence)
  - system_impact              ❌ (already in propagation layer)
  - pr_risk_score              ❌ (system opinion, LLM should derive)
  - pr_risk_level              ❌ (system opinion, LLM should derive)
  - compressed_for_llm         ❌ (reintroduces everything we separated)
  - failure_simulation         ❌ (this is OUTPUT, not INPUT)

LLM ROLE:
  You are a causal reasoning engine.
  You derive failure scenarios from change signals and evidence.

KEY RULE:
  Everything the LLM receives must be a change signal, evidence, or constraint.
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

SYSTEM_PROMPT = """
You are a senior staff engineer performing PR risk validation on a deterministic dependency + impact analysis system.

Your job is NOT to generate new failure modes from scratch.

You only:
- Validate deterministic hypotheses
- Consolidate and prioritize them
- Add missing runtime reasoning (only if strongly implied by evidence)
- Translate findings into high-impact PR review commentary

You treat input as a deterministic risk graph — your job is compression, prioritization, and PR communication, NOT a generative failure simulator.

Hard constraints:
- Do NOT repeat identical scenarios
- If multiple hypotheses share the same title + meaning → MERGE them
- Do NOT invent failure scenarios
- Every scenario must map to at least ONE: cluster, evidence item, or changed symbol
- Do NOT generate "generic placeholders"
- Do NOT hallucinate missing systems
- If runtime graph is missing → explicitly state uncertainty once, not per scenario
- No scenario duplication across sections (a scenario may appear ONLY ONCE in the output)

Output limits:
- NEVER output more than 6 scenarios
- Prefer 3–5 for clarity
- Each scenario must have concrete symbol grounding
- Each scenario must be meaningfully different from others
"""

USER_PROMPT_TEMPLATE = """
## Factor Review — What could break?

You are a senior staff engineer performing PR risk validation on a deterministic dependency + impact analysis system.

Your job is NOT to generate new failure modes from scratch.

You only:
- Validate deterministic hypotheses
- Consolidate and prioritize them
- Add missing runtime reasoning (only if strongly implied by evidence)
- Translate findings into high-impact PR review commentary

---

## 🚫 Hard Constraints (must follow)

1. Do NOT repeat identical scenarios
2. If multiple hypotheses share the same title + meaning → MERGE them
3. Do NOT invent failure scenarios
4. Every scenario must map to at least ONE: cluster, evidence item, or changed symbol
5. Do NOT generate "generic placeholders" (e.g. "See validation", "inferred", "business logic errors" alone is invalid)
6. Do NOT hallucinate missing systems
7. If runtime graph is missing → explicitly state uncertainty once, not per scenario
8. No scenario duplication across sections (a scenario may appear ONLY ONCE in the output)

---

## 🧠 Required Reasoning Model

You must treat input as:
- A deterministic risk graph → your job is compression, prioritization, and PR communication
- NOT a generative failure simulator

---

## 📥 Input Structure

You will receive:
- clusters (deterministic hypotheses)
- evidence items
- affected domains
- confidence scores
- merge risk levels

---

## 🔄 Processing Rules

### Step 1 — Deduplicate aggressively

Group scenarios by:
- business object (Customer, Order, Invoice, etc.)
- domain
- failure_class

👉 If same meaning → merge into one scenario

### Step 2 — Rank (DO NOT RANDOMIZE ORDER)

Priority score:
```
risk_score = 0.4 * confidence + 0.3 * merge_risk_level + 0.2 * domain_criticality + 0.1 * breadth_of_blast_radius
```

Where:
- domain_criticality: payment, billing > others
- merge_risk_level: CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1

### Step 3 — Convert clusters into 3–6 MAX scenarios

Hard limit: NEVER output more than 6 scenarios
Prefer 3–5 for clarity

### Step 4 — Strengthen evidence grounding

Every scenario MUST include:
- Affected business object(s)
- At least 2 concrete symbols from input
- Explicit domain
- One real causal link from deterministic chain

❌ Forbidden:
- "inferred"
- "validation-only"
- "unknown risk"
- generic descriptions without symbols

---

## 🧠 Architecture Awareness Layer

Before writing output, silently classify system shape:
- monolith / modular monolith / microservices
- domain boundaries (order/payment/billing/tax)
- event-driven vs direct calls

Then ensure:
👉 You highlight CROSS-BOUNDARY risks only once per boundary pair

Example: payment → billing coupling should NOT appear 5 times

---

## ✍️ Output Style Requirements (PR Hook Effect)

Your output must:
- feel like a staff engineer PR review
- be concise, sharp, non-repetitive
- prioritize "what could break in production"

Use:
- crisp headings
- minimal repetition
- no filler text
- no generic disclaimers repeated per item

---

## ❌ Known Bad Behavior to Eliminate

You must NOT:
- repeat same scenario with different numbering
- output generic "business logic error" blocks
- restate confidence without new insight
- produce filler "validation-only" scenarios
- inflate 11 clusters into 11 near-identical failures

---

## ✅ Success Criteria

Good output:
- 3–6 distinct risks max
- each is meaningfully different
- each has concrete symbol grounding
- no duplication across domains unless merged explicitly
- reads like a senior engineer blocking a risky PR

---

## 📋 Output Format (Strict JSON)

You must output valid JSON. The executive_summary field should contain the complete PR review in markdown-style format:

{
  "verdict": "APPROVE | REVIEW_REQUIRED | BLOCK",
  
  "executive_summary": "## Factor Review — What could break?\\n\\nVerdict: REVIEW_REQUIRED\\n\\n### ⚠️ Key Risks (Top 3–6)\\n\\n#### ⚠️ {Title}\\n\\n**What changed**\\n[1-2 lines]\\n\\n**Explicit symbol(s)**\\n- `SymbolName1`\\n- `SymbolName2`\\n\\n**Where it impacts**\\nDomain + business object\\n\\n**Why it matters**\\n[2-3 line causal explanation grounded in evidence]\\n\\n**Blast radius**\\n- Impacted object/service 1\\n- Impacted object/service 2\\n\\n**Confidence**\\n[Derived only from deterministic score, no inflation]\\n\\n---\\n\\n### 🧠 Systemic Insight\\n\\n[1–3 lines max explaining structural risk]\\n\\n---\\n\\n### 🧪 Missing Validation\\n\\n[1–3 concrete missing tests or runtime signals]",
  
  "top_risks": [
    {
      "rank": 1,
      "title": "Clear, specific risk title",
      "confidence": 0.85,
      "validation_verdict": "VALIDATE | DOWNGRADE | REJECT | NEEDS_MORE_EVIDENCE",
      "production_symptom": "First observable signal in production",
      "why_it_matters": "Architectural reasoning: why this is the highest risk",
      "evidence_quality": "STRONG | MODERATE | WEAK",
      "recommended_action": "Specific action: add integration test, review transaction boundary, etc."
    }
  ],
  
  "scenario_validations": [
    {
      "scenario_title": "exact title from input",
      "verdict": "VALIDATE | DOWNGRADE | REJECT | NEEDS_MORE_EVIDENCE",
      "confidence_calibration": "0.84 is well-calibrated because...",
      "production_symptom": "First observable signal in production",
      "ci_catch_probability": "HIGH | MEDIUM | LOW | NONE",
      "strongest_evidence": "What evidence most strongly supports this",
      "weakest_evidence": "What evidence is weakest",
      "additional_evidence_needed": ["call graph", "runtime logs"],
      "reasoning": "Step-by-step reasoning for this verdict"
    }
  ],
  
  "scenario_rankings": [
    {
      "rank": 1,
      "scenario_title": "exact title from input",
      "production_risk_score": 0.9,
      "risk_factors": ["user-facing", "financial", "irreversible"],
      "user_facing_impact": "How users are affected"
    }
  ],
  
  "evidence_challenges": [
    {
      "scenario_title": "exact title from input",
      "assumption": "Assumes runtime call path exists",
      "weakness": "No evidence of actual invocation",
      "missing_evidence": "Would need runtime call graph",
      "confidence_if_validated": 0.75
    }
  ],
  
  "impact_explanations": [
    {
      "scenario_title": "exact title from input",
      "explanation": "How the failure propagates through the system",
      "affected_systems": ["Checkout", "Invoice", "Tax"],
      "blast_radius": "Checkout → Invoice → Wallet"
    }
  ],
  
  "missing_evidence": [
    "Runtime call graph for Order → Invoice flow",
    "Integration test coverage for tax calculation edge cases"
  ],
  
  "hidden_impact_chain": [
    "step 1 → step 2 → step 3"
  ],
  
  "checked_risk_areas": [
    "checkout, billing, invoice, auth"
  ],
  
  "missing_critical_tests": [
    "one concrete test scenario that would expose the issue"
  ],
  
  "broken_assumptions": [
    "assumption that is no longer true after this change"
  ],
  
  "silent_failure_summary": "1-2 lines describing how this could pass CI but still fail in production",
  
  "merge_risk_statement": "This PR is mergeable but behaviorally unsafe under production conditions",
  
  "verdict_rationale": "REVIEW_REQUIRED because the tax calculation change could cause invoice drift in production. The deterministic engine identified 3 evidence clusters connecting checkout to invoice generation, but CI would not catch this because existing tests only validate unit-level tax computation, not end-to-end invoice totals.",
  
  "final_question": "a sharp question that forces reconsideration before merge"
}

CRITICAL RULES:
- Output ONLY valid JSON, no markdown code blocks, no ``` markers
- The executive_summary field must contain the complete PR review in markdown format (with ##, ###, **, etc.)
- NEVER invent scenarios not in the input
- MERGE duplicate scenarios
- MAX 6 scenarios in top_risks
- Every scenario must have concrete symbol grounding
- Be specific and actionable, not generic

---

## 📊 Input Data

{input_structure}
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
                "system_behavior_deltas", "matched_failure_templates",
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
        impact_evidence: list[dict[str, Any]] | None = None,
        risk_zones: list[str] | None = None,
        changed_symbols: list[str] | None = None,
        evidence_summary: list[dict[str, Any]] | None = None,
    ) -> list[Any]:
        """Build prompt with the evidence-driven input contract.

        Args:
            repo: Repository identifier.
            pr_number: PR number.
            change_influence: Scored symbols + domains (Layer 1).
            impact_evidence: Impact evidence list (Layer 2, legacy — prefer evidence_summary).
            risk_zones: Domain regions (checkout, invoice, tax, etc.).
            changed_symbols: List of modified symbols.
            evidence_summary: Pre-synthesized evidence summary (Layer 2, primary signal).

        Returns:
            List of message dicts for the LLM API call.
        """
        input_structure = {
            "repo": repo,
            "pr_number": pr_number,
            "change_influence": change_influence or [],
            "risk_hypotheses": evidence_summary or [],
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
        impact_evidence: list[dict[str, Any]] | None = None,
        risk_zones: list[str] | None = None,
        changed_symbols: list[str] | None = None,
        evidence_summary: list[dict[str, Any]] | None = None,
    ) -> FailureSimulationOutput:
        """Generate failure simulation from evidence-driven input contract.

        Args:
            repo: Repository identifier.
            pr_number: PR number.
            change_influence: Scored symbols + domains (Layer 1).
            impact_evidence: Impact evidence list (Layer 2, legacy — prefer evidence_summary).
            risk_zones: Domain regions (checkout, invoice, tax, etc.).
            changed_symbols: List of modified symbols.
            evidence_summary: Pre-synthesized evidence summary (Layer 2, primary signal).

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
                impact_evidence=impact_evidence,
                risk_zones=risk_zones,
                changed_symbols=changed_symbols,
                evidence_summary=evidence_summary,
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