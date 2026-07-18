"""GitHub Comment Generator Orchestration.

Orchestrates the complete pipeline from PresentationIR to rendered markdown:
1. Build LLM context from PresentationIR
2. Build prompts from context
3. Call LLM for structured JSON
4. Parse JSON into GithubComment model
5. Render GithubComment to markdown via Jinja2

This is the single entry point for LLM-enhanced comment generation.
"""

from __future__ import annotations

from typing import Any

from presentation.llm.client import LLMClient
from presentation.llm.context_builder import LLMContextBuilder
from presentation.llm.models import GithubComment, LLMContext
from presentation.llm.parser import LLMResponseParser
from presentation.llm.prompt_builder import PromptBuilder
from presentation.render.github_comment_renderer import GithubCommentRenderer
from runtime.errors import RendererFailed


class GithubCommentGenerator:
    """
    Orchestrates LLM-enhanced GitHub comment generation.
    
    Pipeline:
    PresentationIR → LLMContext → Prompts → LLM JSON → GithubComment → Markdown
    
    Responsibilities:
    - Coordinate all pipeline stages
    - Handle errors and provide fallbacks
    - Ensure deterministic output
    
    This is the ONLY place where the complete pipeline is orchestrated.
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
        Initialize comment generator.
        
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
        self.context_builder = LLMContextBuilder()
        self.prompt_builder = PromptBuilder()
        self.llm_client = LLMClient(api_key=api_key, model=model)
        self.parser = LLMResponseParser()
        self.renderer = GithubCommentRenderer()
        
        # Storage for prompts and raw LLM response (for API exposure)
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None
        self.last_raw_response: str | None = None
    
    def generate(
        self,
        presentation_ir: Any,  # PresentationIR - avoiding circular import
        settings: Any = None,
    ) -> str:
        """
        Generate GitHub comment from PresentationIR.
        
        Args:
            presentation_ir: PresentationIR from Presentation Compiler
            settings: Optional application settings
            
        Returns:
            Rendered markdown comment
            
        Raises:
            RendererFailed: If generation fails completely
        """
        try:
            # Step 1: Build LLM context from PresentationIR
            context = self.context_builder.build(presentation_ir)
            
            # Step 2: Build prompts
            system_prompt, user_prompt = self.prompt_builder.build_prompts(
                context=context,
                repository=self.repository,
                pr_number=self.pr_number,
                language=self.language,
            )
            
            # Store prompts for API exposure
            self.last_system_prompt = system_prompt
            self.last_user_prompt = user_prompt
            
            # Step 3: Call LLM for structured JSON
            try:
                raw_json = self.llm_client.generate_structured_response(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                
                # Store raw response for API exposure
                self.last_raw_response = raw_json
                
                # Step 4: Parse JSON into GithubComment model
                comment = self.parser.parse(raw_json)
                
            except Exception as llm_error:
                # LLM failed - use fallback comment
                comment = self.parser.create_fallback_comment(llm_error)
            
            # Step 5: Render GithubComment to markdown
            markdown = self.renderer.render(comment)
            
            return markdown
            
        except Exception as exc:
            raise RendererFailed(
                f"Failed to generate GitHub comment: {exc}",
                details={"error": str(exc)},
            ) from exc
    
    def generate_from_context(
        self,
        context: LLMContext,
    ) -> str:
        """
        Generate GitHub comment from pre-built LLMContext.
        
        Useful for testing or when context is already built.
        
        Args:
            context: Pre-built LLMContext
            
        Returns:
            Rendered markdown comment
        """
        # Build prompts
        system_prompt, user_prompt = self.prompt_builder.build_prompts(
            context=context,
            repository=self.repository,
            pr_number=self.pr_number,
            language=self.language,
        )
        
        # Store prompts for API exposure
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        
        # Call LLM
        try:
            raw_json = self.llm_client.generate_structured_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            
            # Store raw response for API exposure
            self.last_raw_response = raw_json
            
            # Parse
            comment = self.parser.parse(raw_json)
            
        except Exception as llm_error:
            # Use fallback
            comment = self.parser.create_fallback_comment(llm_error)
        
        # Render
        return self.renderer.render(comment)