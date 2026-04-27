from __future__ import annotations

import json
from typing import Any, Literal

from openai import OpenAI  # pyright: ignore[reportMissingImports]
from pydantic import BaseModel, Field, ValidationError  # pyright: ignore[reportMissingImports]


class FailureScenario(BaseModel):
    title: str
    execution_path: str
    production_impact: str
    confidence: float = Field(ge=0.0, le=1.0)


class FailureSimulationOutput(BaseModel):
    failure_scenarios: list[FailureScenario] = Field(max_length=3)
    hidden_impact_chain: list[str]
    missing_critical_tests: list[str]
    broken_assumptions: list[str]
    verdict: Literal["SAFE", "REVIEW_REQUIRED", "BLOCK_REVIEW"]
    final_question: str


SYSTEM_PROMPT = """You are a senior backend engineer performing pre-merge production failure simulation.
You receive structured PR analysis data.
Your job:
- simulate how production can break
- use only the provided data
- produce concrete execution paths
- identify missing tests
- identify broken assumptions

Strict rules:
- Return JSON only
- Max 3 failure_scenarios
- Do not summarize the PR
- Do not invent files, functions, endpoints, or business logic not provided
- If entry_points is empty, reason from execution_path_hint and changed functions
- Prefer concrete failures over vague risks"""


USER_PROMPT_TEMPLATE = """Analyze this structured PR risk input and return a failure simulation.

Input:
{payload}

Return exactly this JSON shape:
{{
  "failure_scenarios": [
    {{
      "title": "string",
      "execution_path": "string",
      "production_impact": "string",
      "confidence": 0.0
    }}
  ],
  "hidden_impact_chain": ["string"],
  "missing_critical_tests": ["string"],
  "broken_assumptions": ["string"],
  "verdict": "SAFE | REVIEW_REQUIRED | BLOCK_REVIEW",
  "final_question": "string"
}}"""


class FailureSimulationLLM:
    def __init__(
        self,
        api_key: str,
        model: str = "llama3.1-8b",
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
            temperature=0.2,
        )

        raw = completion.choices[0].message.content or "{}"

        try:
            data = json.loads(raw)
            return FailureSimulationOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            raise ValueError(f"Invalid failure simulation output: {e}\nRaw: {raw}") from e
