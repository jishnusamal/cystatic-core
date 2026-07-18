"""LLM Client for OpenAI integration.

Handles communication with OpenAI API.
No presentation logic - just API calls, retries, and timeouts.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


class LLMClient:
    """
    Client for OpenAI API.
    
    Responsibilities:
    - API key management
    - Model configuration
    - Retry logic
    - Timeout handling
    - Request/response serialization
    
    No presentation logic. No parsing logic.
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "openai/gpt-oss-120b",
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: int = 60,
        max_retries: int = 3,
        base_url: str = "https://api.groq.com/openai/v1",
    ):
        """
        Initialize LLM client.
        
        Args:
            api_key: OpenAI API key. If None, reads from OPENAI_API_KEY env var.
            model: Model name (e.g., "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo").
            temperature: Sampling temperature (0.0-2.0). Lower = more deterministic.
            max_tokens: Maximum tokens in response.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries on failure.
            base_url: Base URL for the OpenAI API.
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Provide api_key or set OPENAI_API_KEY environment variable."
            )
        
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = base_url
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key, timeout=timeout, max_retries=max_retries, base_url=self.base_url)
    
    def generate_structured_response(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Generate a structured JSON response from prompts.
        
        Args:
            system_prompt: System prompt defining Factor's philosophy and constraints.
            user_prompt: User prompt containing serialized LLMContext.
            
        Returns:
            Generated JSON string (not markdown).
            
        Raises:
            RuntimeError: If generation fails after retries.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            # Extract generated content
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if content:
                    return content.strip()
            
            raise RuntimeError("OpenAI returned empty response")
            
        except Exception as exc:
            raise RuntimeError(f"LLM generation failed: {exc}") from exc
    
    def generate_comment(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Generate a PR comment from prompts (legacy method).
        
        Args:
            system_prompt: System prompt defining Factor's philosophy and constraints.
            user_prompt: User prompt containing serialized LLMContext.
            
        Returns:
            Generated markdown comment.
            
        Raises:
            RuntimeError: If generation fails after retries.
            
        Note:
            This method is deprecated. Use generate_structured_response() instead
            for the new JSON-based pipeline.
        """
        # Delegate to structured response for backward compatibility
        return self.generate_structured_response(system_prompt, user_prompt)
    
    def get_model_info(self) -> dict[str, Any]:
        """
        Get information about the configured model.
        
        Returns:
            Dictionary with model configuration.
        """
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }