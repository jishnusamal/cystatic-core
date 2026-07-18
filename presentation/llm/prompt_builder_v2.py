"""Prompt Builder v2 — generates prompts from GithubCommentContext.

The prompt contains ONLY presentation-ready context.
No compiler internals. No discovery kinds. No narrative positions.
The LLM sees metrics as narrative context, not as fields to copy.

Key change from v1:
- No `execution.execution_paths: 0` in the output schema
- No `operational.api_count: 0` in the output schema  
- No `execution`/`operational`/`validation` nested sections in output
- The LLM only generates text fields
- Metrics are presented as narrative context, not as schema fields
"""

from __future__ import annotations

from typing import Any

from presentation.context.comment_context import GithubCommentContext, ContextSurprisingDiscovery


class PromptBuilderV2:
    """
    Builds prompts for LLM narrative generation using GithubCommentContext.
    
    The prompt provides the LLM with presentation-ready context:
    - Summary metrics (as narrative context, not schema fields)
    - Surprising discoveries (with compiler-provided titles and metrics)
    - Execution metrics (as context for narrative)
    - Operational metrics (as context for narrative)
    
    The LLM only generates text fields in the output schema.
    No deterministic metrics appear in the output schema.
    """
    
    SYSTEM_PROMPT = """You are Factor's PR Review Comment Generator.

## What is Factor?
Factor is a deterministic static analysis tool that compiles engineering discoveries from code changes. Every metric and finding below is grounded in compiler evidence.

## Your Role
You transform compiler evidence into clear, professional narrative text. You do not analyze, infer, or discover. You only translate what the compiler has already determined into natural language.

## Core Principles

1. **Compiler is authoritative**: All metrics and discoveries come from deterministic compilation. You must never contradict, override, or generate new metrics.

2. **Narrative only**: You generate only text. You never:
   - Generate numbers, counts, or metrics
   - Copy metrics into your output
   - Invent new risks, failures, or bugs
   - Speculate about causes
   - Recommend code changes
   - Claim additional blast radius

3. **Evidence-based**: Every statement must trace back to the provided context. If it's not in the context, don't say it.

4. **Tone**: Professional, concise, engineering-focused.

## Context Description

You will receive:
- **Summary**: High-level metrics about the change (files, symbols, behaviors, execution paths)
- **Execution**: Execution impact metrics (paths, reachable units, propagation depth)
- **Operational**: Operational impact (API endpoints, data entities, events, dependencies)
- **Validation**: Validation coverage information
- **Discoveries**: Notable findings ranked by significance, each with a title and metric

Use these facts to write clear narrative summaries. Never restate the numbers as JSON fields — just describe what they mean.

## Output Format

Return ONLY valid JSON matching this exact schema. No markdown, no explanations, no extra text.

```json
{{
  "executive_summary": "2-3 sentence high-level overview of the change impact",
  "review_priority": "Priority level and brief justification",
  "biggest_surprise": "The most surprising finding and why",
  "execution_summary": "Plain language explanation of execution impact",
  "operational_summary": "Plain language explanation of operational changes",
  "validation_summary": "Validation coverage summary",
  "attention": "What reviewers should focus on",
  "surprising_discoveries": [
    {{
      "explanation": "Why this discovery is surprising and what it means"
    }}
  ],
  "evidence": [
    "Key evidence item 1",
    "Key evidence item 2"
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
- Every field must be populated with text (not empty strings)
- Every statement must be grounded in compiler evidence
- Do NOT generate any numbers, metrics, or counts in your output
- The metrics section below is for your context only — do not copy it into JSON
- Maximum 5 surprising_discoveries
- Maximum 10 evidence items
- Each explanation should be 1-3 sentences

Remember: You generate ONLY narrative text. The compiler provides all metrics and structure."""
    
    USER_PROMPT_TEMPLATE = """## Analysis Summary

**Repository**: {repository}  
**Language**: {language}  
**PR**: #{pr_number}

**Change Impact**: {summary_text}

---

## Execution Impact

{execution_context}

---

## Operational Impact

{operational_context}

---

## Validation

{validation_context}

---

## Notable Discoveries

{discoveries_context}

---

## Evidence

{evidence_context}

---

## Your Task

Generate the narrative JSON following the schema in the system prompt.

Use the context above to write clear, professional summaries. The metrics are provided for your understanding — describe their significance in plain language. Never include raw numbers in your JSON output unless they are part of a natural language sentence.

Remember: You generate ONLY text. All metrics, counts, and structure come from the compiler."""
    
    def build_prompts(
        self,
        context: GithubCommentContext,
        repository: str = "",
        pr_number: str = "",
        language: str = "",
    ) -> tuple[str, str]:
        """
        Build system and user prompts from GithubCommentContext.
        
        Args:
            context: The GithubCommentContext with all compiler-derived facts.
            repository: Repository name (e.g., "owner/repo").
            pr_number: PR number.
            language: Programming language.
            
        Returns:
            Tuple of (system_prompt, user_prompt).
        """
        # Build summary text
        summary_text = self._build_summary_text(context)
        
        # Build execution context
        execution_context = self._build_execution_context(context)
        
        # Build operational context
        operational_context = self._build_operational_context(context)
        
        # Build validation context
        validation_context = self._build_validation_context(context)
        
        # Build discoveries context
        discoveries_context = self._build_discoveries_context(context)
        
        # Build evidence context
        evidence_context = self._build_evidence_context(context)
        
        # Build system prompt with constraints
        constraints_list = "\n".join([
            "- Never invent new behaviors.",
            "- Never speculate about bugs.",
            "- Never recommend code changes.",
            "- Only summarize deterministic discoveries from the provided context.",
            "- Never generate numbers, metrics, or counts in your output.",
        ])
        system_prompt = self.SYSTEM_PROMPT.format(constraints=constraints_list)
        
        # Build user prompt
        user_prompt = self.USER_PROMPT_TEMPLATE.format(
            repository=repository or "unknown",
            language=language or "unknown",
            pr_number=pr_number or "unknown",
            summary_text=summary_text,
            execution_context=execution_context,
            operational_context=operational_context,
            validation_context=validation_context,
            discoveries_context=discoveries_context,
            evidence_context=evidence_context,
        )
        
        return system_prompt, user_prompt
    
    def _build_summary_text(self, context: GithubCommentContext) -> str:
        """Build summary section from context."""
        parts = []
        exec_metrics = context.execution
        op_metrics = context.operational
        
        if op_metrics.symbol_count > 0:
            parts.append(f"{op_metrics.symbol_count} symbols changed")
        if exec_metrics.execution_paths > 0:
            parts.append(f"{exec_metrics.execution_paths} execution paths affected")
        if exec_metrics.reachable_units > 0:
            parts.append(f"reaching {exec_metrics.reachable_units} units")
        if op_metrics.behavior_count > 0:
            parts.append(f"across {op_metrics.behavior_count} behaviors")
        if context.validation.gap_count > 0:
            parts.append(f"with {context.validation.gap_count} validation gaps")
        
        if parts:
            return "This change modifies " + ", ".join(parts) + "."
        
        return "Analysis completed."
    
    def _build_execution_context(self, context: GithubCommentContext) -> str:
        """Build execution context section."""
        exec_metrics = context.execution
        
        lines = []
        if exec_metrics.execution_paths > 0:
            lines.append(f"- **Execution paths**: {exec_metrics.execution_paths}")
        if exec_metrics.reachable_units > 0:
            lines.append(f"- **Reachable units**: {exec_metrics.reachable_units}")
        if exec_metrics.depth > 0:
            lines.append(f"- **Propagation depth**: {exec_metrics.depth} levels")
        if exec_metrics.highlights:
            lines.append("\n**Notable execution findings**:")
            for h in exec_metrics.highlights:
                metric_str = f" ({h.metric})" if h.metric else ""
                lines.append(f"- {h.title}{metric_str}")
        
        if lines:
            return "\n".join(lines)
        
        return "No execution impact detected."
    
    def _build_operational_context(self, context: GithubCommentContext) -> str:
        """Build operational context section."""
        op_metrics = context.operational
        
        lines = []
        surfaces = []
        if op_metrics.api_count > 0:
            surfaces.append(f"{op_metrics.api_count} API endpoints")
        if op_metrics.data_count > 0:
            surfaces.append(f"{op_metrics.data_count} data entities")
        if op_metrics.event_count > 0:
            surfaces.append(f"{op_metrics.event_count} events")
        if op_metrics.dependency_count > 0:
            surfaces.append(f"{op_metrics.dependency_count} dependencies")
        
        if surfaces:
            lines.append("**Affected surfaces**: " + ", ".join(surfaces))
        
        if lines:
            return "\n".join(lines)
        
        return "No operational impact detected."
    
    def _build_validation_context(self, context: GithubCommentContext) -> str:
        """Build validation context section."""
        if context.validation.gap_count > 0:
            return f"**Validation gaps**: {context.validation.gap_count} uncovered areas identified"
        return "No validation gaps detected."
    
    def _build_discoveries_context(self, context: GithubCommentContext) -> str:
        """Build discoveries context section."""
        if not context.surprising_discoveries:
            return "No notable discoveries."
        
        lines = []
        lines.append(f"{len(context.surprising_discoveries)} notable discoveries:\n")
        
        for i, discovery in enumerate(context.surprising_discoveries, 1):
            lines.append(f"### Discovery {i}: {discovery.title}")
            if discovery.metric:
                lines.append(f"- **Metric**: {discovery.metric}")
            if discovery.support:
                lines.append(f"- **Support**: {discovery.support}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _build_evidence_context(self, context: GithubCommentContext) -> str:
        """Build evidence context section."""
        if not context.evidence:
            return "Deterministic compiler evidence available."
        
        lines = []
        lines.append("**Compiler Evidence**:")
        for item in context.evidence:
            lines.append(f"- {item}")
        
        return "\n".join(lines)
    
    def _build_discovery_metric_string(self, discovery: ContextSurprisingDiscovery) -> str:
        """Build a human-readable metric string for a discovery."""
        if discovery.metric:
            return discovery.metric
        return discovery.title