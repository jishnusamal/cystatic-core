"""GitHub Comment Renderer.

Renders GithubComment models to GitHub Markdown using Jinja2 templates.
Contains zero business logic - pure presentation transformation.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from presentation.llm.models import GithubComment
from presentation.render.environment import JinjaEnvironment


class GithubCommentRenderer:
    """
    Renders GithubComment models to GitHub Markdown.
    
    Responsibilities:
    - Load Jinja2 template
    - Render GithubComment to markdown
    - Ensure deterministic output (same input = same output)
    
    No business logic. No content generation.
    """
    
    TEMPLATE_NAME = "github_comment.md.j2"
    
    def __init__(self):
        """Initialize renderer with Jinja2 environment."""
        self.env = JinjaEnvironment.get_environment()
        self.template = self.env.get_template(self.TEMPLATE_NAME)
    
    def render(self, comment: GithubComment) -> str:
        """
        Render a GithubComment to GitHub Markdown.
        
        Args:
            comment: Structured GithubComment model from LLM
            
        Returns:
            Rendered markdown string
            
        Raises:
            RuntimeError: If rendering fails
        """
        try:
            # Convert dataclass to dict for template rendering
            comment_dict = asdict(comment)
            
            # Render template
            markdown = self.template.render(**comment_dict)
            
            # Ensure consistent trailing newline
            markdown = markdown.rstrip() + "\n"
            
            return markdown
            
        except Exception as exc:
            raise RuntimeError(f"Failed to render GitHub comment: {exc}") from exc
    
    def render_to_string(self, comment: GithubComment) -> str:
        """
        Alias for render() for clarity in pipeline.
        
        Args:
            comment: Structured GithubComment model from LLM
            
        Returns:
            Rendered markdown string
        """
        return self.render(comment)