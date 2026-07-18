"""Prompt Builder for LLM Comment Generation.

Constructs system and user prompts from LLMContext.
The system prompt defines Factor's philosophy and constraints.
The user prompt contains only the serialized context.
"""

from __future__ import annotations

from typing import Any

from presentation.llm.models import LLMContext, LLMDiscovery, LLMNarrative, LLMVisual

class PromptBuilder:
    """
    Builds prompts for LLM comment generation.
    
    Responsibilities:
    - Define system prompt with Factor philosophy and constraints
    - Serialize LLMContext into user prompt
    - Enforce that LLM cannot invent discoveries
    """
    
    # System prompt is static - defines the contract
    # Note: Double curly braces {{}} are escaped for .format() method
    SYSTEM_PROMPT = """You are Factor's PR Review Comment Generator.

## What is Factor?
Factor is a deterministic static analysis tool that compiles engineering discoveries from code changes. Every statement in the provided context is grounded in compiler evidence.

## Core Principles

1. **Compiler is authoritative**: All discoveries come from deterministic compilation. You must never contradict or override them.

2. **No invented discoveries**: You may ONLY:
   - Summarize existing discoveries
   - Prioritize by significance
   - Explain technical impact
   - Organize for readability
   - Rewrite in natural language
   
   You must NEVER:
   - Add new risks or failures
   - Infer bugs not in the context
   - Speculate about causes
   - Recommend code changes
   - Add metrics not provided
   - Claim additional blast radius

3. **Evidence-based only**: Every claim must trace back to the provided discoveries. If it's not in the context, don't say it.

4. **Tone**: Professional, concise, engineering-focused.

## Output Format

Return ONLY valid JSON matching this exact schema. No markdown, no explanations, no extra text.

```json
{{
  "executive_summary": "2-3 sentence high-level overview of the change impact",
  "review_priority": "Priority level and brief justification",
  "biggest_surprise": "The most surprising finding and why",
  "execution_summary": "Plain language explanation of execution impact",
  "operational_summary": "Plain language explanation of operational changes",
  "surprising_discoveries": [
    {{
      "title": "Discovery title",
      "explanation": "Why it's surprising",
      "metric": "Key metric (e.g., '315 units reached')",
      "support": "Supporting evidence or context"
    }}
  ],
  "execution": {{
    "execution_paths": 0,
    "reachable_units": 0,
    "depth": 0,
    "highlights": []
  }},
  "operational": {{
    "api_count": 0,
    "data_count": 0,
    "event_count": 0,
    "dependency_count": 0
  }},
  "validation": {{
    "summary": "Validation coverage summary"
  }},
  "evidence": [
    "Evidence item 1",
    "Evidence item 2"
  ]
}}
```

## Constraints

{constraints}

## Critical Rules

- Return ONLY the JSON object
- Do NOT wrap in markdown code blocks
- Do NOT include any explanatory text before or after
- Do NOT include comments in the JSON
- Every field must be populated
- Every statement must be grounded in compiler evidence
- If a field has no data, use an empty string or appropriate default
- Maximum 5 surprising_discoveries
- Maximum 10 evidence items

Remember: You are a translator from compiler output to structured JSON. You do not analyze, infer, or discover. You only render what the compiler has already determined."""

    USER_PROMPT_TEMPLATE = """## Analysis Context

Repository: {repository}
Language: {language}
PR: #{pr_number}

## Compiler Summary

{summary}

## Discoveries (Ranked by Significance)

{discoveries_section}

## Narrative Structure

{narrative_section}

## Visual Semantics

{visuals_section}

## Your Task

Transform the above deterministic discoveries into structured JSON following the exact schema provided in the system prompt.

1. executive_summary: 2-3 sentence overview
2. review_priority: Priority level with justification
3. biggest_surprise: Most surprising finding
4. execution_summary: Execution impact in plain language
5. operational_summary: Operational changes in plain language
6. surprising_discoveries: Top discoveries (max 5)
7. execution: Execution metrics (execution_paths, reachable_units, depth, highlights)
8. operational: Operational metrics (api_count, data_count, event_count, dependency_count)
9. validation: Validation summary
10. evidence: Key evidence items (max 10)

Remember: Only use the provided data. Never invent or speculate. Return ONLY valid JSON."""

    def build_prompts(self, context: LLMContext, repository: str = "", pr_number: str = "", language: str = "") -> tuple[str, str]:
        """
        Build system and user prompts from LLMContext.
        
        Args:
            context: The LLMContext to transform into prompts.
            repository: Repository name (e.g., "owner/repo").
            pr_number: PR number.
            language: Programming language.
            
        Returns:
            Tuple of (system_prompt, user_prompt).
        """
        # Build system prompt with constraints
        constraints_list = "\n".join(f"- {c}" for c in context.constraints)
        system_prompt = self.SYSTEM_PROMPT.format(constraints=constraints_list)
        
        # Build user prompt with serialized context
        user_prompt = self.USER_PROMPT_TEMPLATE.format(
            repository=repository or "unknown",
            language=language or "unknown",
            pr_number=pr_number or "unknown",
            summary=self._serialize_summary(context.summary),
            discoveries_section=self._serialize_discoveries(context.discoveries),
            narrative_section=self._serialize_narrative(context.narrative),
            visuals_section=self._serialize_visuals(context.visuals),
        )
        
        return system_prompt, user_prompt
    
    def _serialize_summary(self, summary: dict[str, Any]) -> str:
        """Serialize summary section."""
        if not summary:
            return "No summary available."
        
        lines = []
        lines.append(f"- **Changed files**: {summary.get('changed_files', 0)}")
        lines.append(f"- **Changed symbols**: {summary.get('changed_symbols', 0)}")
        lines.append(f"- **Affected behaviors**: {summary.get('affected_behaviors', 0)}")
        lines.append(f"- **Execution paths**: {summary.get('execution_paths', 0)}")
        lines.append(f"- **Services reached**: {summary.get('services_reached', 0)}")
        lines.append(f"- **Validation gaps**: {summary.get('validation_gaps', 0)}")
        lines.append(f"- **Surprising discoveries**: {summary.get('surprising_discoveries', 0)}")
        
        return "\n".join(lines)
    
    def _serialize_discoveries(self, discoveries: tuple[LLMDiscovery, ...]) -> str:
        """Serialize discoveries section."""
        if not discoveries:
            return "No discoveries."
        
        lines = []
        lines.append(f"Total discoveries: {len(discoveries)}\n")
        
        for i, discovery in enumerate(discoveries, 1):
            lines.append(f"### Discovery {i}: {discovery.title}")
            lines.append(f"**Kind**: {discovery.kind}")
            lines.append(f"**Summary**: {discovery.summary}")
            lines.append(f"**Narrative position**: {discovery.narrative_position}")
            
            if discovery.metrics:
                lines.append("\n**Metrics**:")
                for key, value in discovery.metrics.items():
                    if value:  # Only show non-zero metrics
                        lines.append(f"  - {key}: {value}")
            
            if discovery.surprise:
                lines.append("\n**Surprise**:")
                if discovery.surprise.get("description"):
                    lines.append(f"  - {discovery.surprise['description']}")
                if discovery.surprise.get("max_ratio"):
                    lines.append(f"  - Max ratio: {discovery.surprise['max_ratio']:.2f}")
            
            if discovery.top_evidence:
                lines.append("\n**Top evidence**:")
                for evidence in discovery.top_evidence:
                    lines.append(f"  - {evidence}")
            
            lines.append("")  # Blank line between discoveries
        
        return "\n".join(lines)
    
    def _serialize_narrative(self, narrative: tuple[LLMNarrative, ...]) -> str:
        """Serialize narrative section."""
        if not narrative:
            return "No narrative structure."
        
        lines = []
        lines.append("Narrative sections (in order):\n")
        
        for section in sorted(narrative, key=lambda s: s.order):
            lines.append(f"{section.order}. **{section.section}**: {section.description}")
            if section.discovery_ids:
                lines.append(f"   Discoveries: {', '.join(section.discovery_ids[:5])}")
        
        return "\n".join(lines)
    
    def _serialize_visuals(self, visuals: tuple[LLMVisual, ...]) -> str:
        """Serialize visuals section."""
        if not visuals:
            return "No visuals."
        
        lines = []
        lines.append(f"Total visuals: {len(visuals)}\n")
        
        # Group by discovery
        by_discovery: dict[str, list[LLMVisual]] = {}
        for visual in visuals:
            if visual.discovery_id not in by_discovery:
                by_discovery[visual.discovery_id] = []
            by_discovery[visual.discovery_id].append(visual)
        
        for discovery_id, visual_list in list(by_discovery.items())[:10]:  # Limit to 10 discoveries
            lines.append(f"\n**{discovery_id}**:")
            for visual in visual_list:
                lines.append(f"  - {visual.semantic}: {visual.label} = {visual.value}")
        
        return "\n".join(lines)