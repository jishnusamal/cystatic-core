"""Jinja2 Environment Configuration.

Single shared Jinja2 environment for all template rendering.
No template loading elsewhere - all rendering goes through this environment.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


class JinjaEnvironment:
    """
    Singleton Jinja2 environment for Factor templates.
    
    Responsibilities:
    - Configure Jinja2 with safe defaults
    - Load templates from the templates directory
    - Provide single shared environment instance
    
    No business logic. No template-specific configuration.
    """
    
    _instance: Environment | None = None
    
    @classmethod
    def get_environment(cls) -> Environment:
        """
        Get the shared Jinja2 environment.
        
        Returns:
            Configured Jinja2 Environment instance
        """
        if cls._instance is None:
            # Determine templates directory
            # Assumes templates/ is at project root (sibling of presentation/)
            templates_dir = Path(__file__).parent.parent.parent / "templates"
            
            cls._instance = Environment(
                loader=FileSystemLoader(str(templates_dir)),
                autoescape=False,  # We control escaping in templates
                trim_blocks=True,  # Remove first newline after block
                lstrip_blocks=True,  # Strip leading whitespace from blocks
                keep_trailing_newline=True,  # Preserve trailing newlines
            )
        
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset the environment (for testing)."""
        cls._instance = None