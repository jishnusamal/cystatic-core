"""GitHub Comment Generator v2 — Orchestrates the complete pipeline.

Pipeline:
    PresentationIR → PresentationContextBuilder (deterministic)
                       ↓
    GithubCommentContext (all metrics from compiler)
                       ↓
    PromptBuilderV2 → LLM → NarrativeParser (narrative only)
                       ↓
    GithubCommentNarrative (text only, no metrics)
                       ↓
    ContextMerger → GithubComment (merged)
                       ↓
    Jinja2 Renderer → Markdown

Key improvements over v1:
1. All deterministic metrics originate from the compiler via PresentationContextBuilder
2. The LLM never generates, copies, or reconstructs numerical data
3. The prompt contains only presentation-ready context (no compiler internals)
4. Jinja renders from a stable GithubCommentContext via the merger
5. Fallback comments only appear on genuine failures
6. Each pipeline stage is independently observable through structured diagnostics
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from presentation.context import (
    GithubCommentContext,
    PresentationContextBuilder,
    ContextMerger,
)
from presentation.llm.client import LLMClient
from presentation.llm.narrative_models import GithubCommentNarrative
from presentation.llm.narrative_parser import NarrativeParser
from presentation.llm.prompt_builder_v2 import PromptBuilderV2
from presentation.llm.models import GithubComment
from presentation.render.github_comment_renderer import GithubCommentRenderer
from runtime.errors import RendererFailed

logger = logging.getLogger(__name__)


# Diagnostic stages for pipeline observability
STAGE_COMPILER = "compiler_context"
STAGE_PROMPT = "prompt_building"
STAGE_LLM = "llm_generation"
STAGE_PARSE = "narrative_parse"
STAGE_MERGE = "context_merge"
STAGE_RENDER = "rendering"


class GithubCommentGeneratorV2:
    """
    Orchestrates the complete pipeline from PresentationIR to rendered markdown.
    
    Uses the new architecture:
    - GithubCommentContext owns all deterministic metrics
    - GithubCommentNarrative owns only text (LLM-generated)
    - ContextMerger produces the final GithubComment
    - Jinja2 renders to markdown
    
    Diagnostics are tracked at every stage for observability.
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "openai/gpt-oss-120b",
        repository: str = "",
        pr_number: str = "",
        language: str = "",
    ):
        """
        Initialize comment generator v2.
        
        Args:
            api_key: OpenAI API key. If None, reads from settings or environment.
            model: LLM model name.
            repository: Repository name (e.g., "owner/repo").
            pr_number: PR number.
            language: Programming language.
        """
        self.repository = repository
        self.pr_number = pr_number
        self.language = language
        
        # Initialize pipeline components
        self.context_builder = PresentationContextBuilder()
        self.prompt_builder = PromptBuilderV2()
        self.llm_client = LLMClient(api_key=api_key, model=model)
        self.narrative_parser = NarrativeParser()
        self.context_merger = ContextMerger()
        self.renderer = GithubCommentRenderer()
        
        # Pipeline diagnostics tracker
        self._diagnostics: dict[str, Any] = {
            "stages": {},
            "success": False,
            "narrative_source": "none",
        }
    
    def generate(
        self,
        presentation_ir: Any,  # PresentationIR
        settings: Any = None,
    ) -> dict[str, Any]:
        """
        Generate GitHub comment from PresentationIR.
        
        Args:
            presentation_ir: PresentationIR from Presentation Compiler
            settings: Optional application settings
            
        Returns:
            Dictionary with:
            - generated: bool (whether LLM narrative was used)
            - comment: str (rendered markdown)
            - diagnostics: dict (per-stage diagnostic info)
            - llm_success: bool
            - parse_success: bool
            - render_success: bool
        """
        result: dict[str, Any] = {
            "generated": False,
            "llm_success": False,
            "parse_success": False,
            "render_success": False,
            "comment": "",
            "diagnostics": {},
        }
        
        try:
            # =========================================================================
            # Stage 1: Build deterministic context from PresentationIR
            # =========================================================================
            logger.info("[comment-gen-v2] Stage 1: Building compiler context")
            context = self.context_builder.build(presentation_ir)
            self._diagnostics["stages"][STAGE_COMPILER] = {
                "success": True,
                "discovery_count": len(context.surprising_discoveries),
                "evidence_count": len(context.evidence),
                "execution_paths": context.execution.execution_paths,
                "reachable_units": context.execution.reachable_units,
                "api_count": context.operational.api_count,
                "data_count": context.operational.data_count,
            }
            
            # =========================================================================
            # Stage 2: Build prompts from context
            # =========================================================================
            logger.info("[comment-gen-v2] Stage 2: Building prompts")
            system_prompt, user_prompt = self.prompt_builder.build_prompts(
                context=context,
                repository=self.repository,
                pr_number=self.pr_number,
                language=self.language,
            )
            self._diagnostics["stages"][STAGE_PROMPT] = {
                "success": True,
                "system_prompt_length": len(system_prompt),
                "user_prompt_length": len(user_prompt),
            }
            
            # =========================================================================
            # Stage 3: Call LLM for narrative generation
            # =========================================================================
            logger.info("[comment-gen-v2] Stage 3: Calling LLM")
            llm_narrative = GithubCommentNarrative()
            llm_success = False
            
            try:
                raw_json = self.llm_client.generate_structured_response(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                self._diagnostics["stages"][STAGE_LLM] = {
                    "success": True,
                    "response_length": len(raw_json),
                    "raw_response_preview": raw_json[:200],
                }
                
                # =========================================================================
                # Stage 4: Parse LLM response into narrative
                # =========================================================================
                logger.info("[comment-gen-v2] Stage 4: Parsing narrative")
                llm_narrative = self.narrative_parser.parse(raw_json)
                llm_success = True
                self._diagnostics["stages"][STAGE_PARSE] = {
                    "success": True,
                    "has_executive_summary": bool(llm_narrative.executive_summary),
                    "has_review_priority": bool(llm_narrative.review_priority),
                    "discovery_count": len(llm_narrative.surprising_discoveries),
                    "evidence_count": len(llm_narrative.evidence),
                }
                
            except Exception as llm_error:
                logger.warning(f"[comment-gen-v2] LLM narrative generation failed: {llm_error}")
                self._diagnostics["stages"][STAGE_LLM] = {
                    "success": False,
                    "error": str(llm_error),
                }
                self._diagnostics["stages"][STAGE_PARSE] = {
                    "success": False,
                    "error": "LLM call failed, no response to parse",
                }
                
                # Build diagnostic context (compiler-only fallback)
                context = self.context_builder.build_diagnostic_context(presentation_ir)
                llm_narrative = GithubCommentNarrative()
            
            result["llm_success"] = llm_success
            
            # =========================================================================
            # Stage 5: Merge context with narrative
            # =========================================================================
            logger.info("[comment-gen-v2] Stage 5: Merging context with narrative")
            try:
                comment = self.context_merger.merge(context, llm_narrative)
                self._diagnostics["stages"][STAGE_MERGE] = {
                    "success": True,
                    "merged_discoveries": len(comment.surprising_discoveries),
                    "has_execution_metrics": comment.execution.execution_paths > 0,
                    "has_operational_metrics": comment.operational.api_count > 0,
                    "narrative_source": "llm" if llm_success else "compiler_fallback",
                }
            except Exception as merge_error:
                logger.error(f"[comment-gen-v2] Merge failed: {merge_error}")
                self._diagnostics["stages"][STAGE_MERGE] = {
                    "success": False,
                    "error": str(merge_error),
                }
                raise
            
            # =========================================================================
            # Stage 6: Render to markdown
            # =========================================================================
            logger.info("[comment-gen-v2] Stage 6: Rendering to markdown")
            try:
                markdown = self.renderer.render(comment)
                self._diagnostics["stages"][STAGE_RENDER] = {
                    "success": True,
                    "markdown_length": len(markdown),
                }
                result["render_success"] = True
            except Exception as render_error:
                logger.error(f"[comment-gen-v2] Render failed: {render_error}")
                self._diagnostics["stages"][STAGE_RENDER] = {
                    "success": False,
                    "error": str(render_error),
                }
                raise
            
            # =========================================================================
            # Build result
            # =========================================================================
            result["generated"] = llm_success
            result["comment"] = markdown
            result["llm_success"] = llm_success
            result["parse_success"] = llm_success
            result["diagnostics"] = dict(self._diagnostics)
            
            self._diagnostics["success"] = True
            self._diagnostics["narrative_source"] = "llm" if llm_success else "compiler_fallback"
            
            return result
            
        except Exception as exc:
            logger.error(f"[comment-gen-v2] Pipeline failed: {exc}")
            self._diagnostics["success"] = False
            result["diagnostics"] = dict(self._diagnostics)
            result["comment"] = self._render_fallback_comment(presentation_ir)
            result["render_success"] = True
            
            raise RendererFailed(
                f"Failed to generate GitHub comment: {exc}",
                details={"diagnostics": self._diagnostics, "error": str(exc)},
            ) from exc
    
    def _render_fallback_comment(self, presentation_ir: Any) -> str:
        """Render a minimal fallback comment when the pipeline fails completely."""
        try:
            # Build minimal context from presentation IR
            context = self.context_builder.build_diagnostic_context(presentation_ir)
            
            # Create a minimal GithubComment
            from presentation.llm.models import GithubComment as OldGithubComment
            comment = OldGithubComment(
                executive_summary=context.executive_summary,
                review_priority=context.review_priority,
                biggest_surprise=context.biggest_surprise,
                execution_summary=context.execution_summary,
                operational_summary=context.operational_summary,
                validation_summary=context.validation_summary,
                attention=context.attention,
                execution={
                    "execution_paths": context.execution.execution_paths,
                    "reachable_units": context.execution.reachable_units,
                    "depth": context.execution.depth,
                    "highlights": [
                        {
                            "title": h.title,
                            "explanation": h.explanation,
                            "metric": h.metric,
                            "support": h.support,
                        }
                        for h in context.execution.highlights
                    ],
                },
                operational={
                    "api_count": context.operational.api_count,
                    "data_count": context.operational.data_count,
                    "event_count": context.operational.event_count,
                    "dependency_count": context.operational.dependency_count,
                },
                validation={
                    "summary": context.validation.summary,
                },
                evidence=context.evidence,
            )
            return self.renderer.render(comment)
        except Exception:
            # Ultimate fallback
            return """## ⚠️ Analysis Complete

Factor analysis completed. Please view the full results in the API response.

<sub>Generated by **Factor** — Deterministic Engineering Discovery Compiler</sub>"""
    
    def get_diagnostics(self) -> dict[str, Any]:
        """Get current pipeline diagnostics."""
        return dict(self._diagnostics)