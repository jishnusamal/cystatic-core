"""Test for public PR analysis endpoint with missing token."""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException
from api.user.urls import analyze_public_pr
from schemas import AnalyzeRequest
from core_engine.graph.reasoning_packet import ReasoningPacket


def test_analyze_public_pr_without_token():
    """Test that public PR endpoint works without a GitHub token."""
    # Create a mock request
    mock_request = AnalyzeRequest(
        repo="owner/repo",
        pr_number=123,
        installation_id=None,
    )
    
    # Mock the settings to return empty token
    with patch('api.user.urls.settings') as mock_settings:
        mock_settings.github_access_token = ""
        mock_settings.llm_api_key = None
        mock_settings.ai_api_key = None
        mock_settings.llm_model = "test-model"
        mock_settings.llm_base_url = "https://test.com"
        
        # Mock build_public_github_client to verify it's called with None
        with patch('api.user.urls.build_public_github_client') as mock_build_client:
            mock_source = Mock()
            mock_source.fetch_diff.return_value = Mock()  # Return a mock diff
            mock_build_client.return_value = mock_source
            
            # Mock PythonAdapter and CorePipeline
            with patch('api.user.urls.PythonAdapter') as mock_adapter_class:
                mock_language = Mock()
                mock_language.analyze.return_value = Mock()  # Return a mock semantic graph
                mock_adapter_class.return_value = mock_language
                
                with patch('api.user.urls.CorePipeline') as mock_pipeline_class:
                    mock_pipeline = Mock()
                    mock_reasoning_packet = ReasoningPacket(
                        summary="Test summary",
                        changed_areas=["area1"],
                        unresolved=["issue1"]
                    )
                    mock_pipeline.run.return_value = mock_reasoning_packet
                    mock_pipeline_class.return_value = mock_pipeline
                    
                    # Call the endpoint (it's async, so we need to run it)
                    result = asyncio.run(analyze_public_pr(body=mock_request))
                    
                    # Verify build_public_github_client was called with None (not empty string)
                    mock_build_client.assert_called_once_with(token=None)
                    
                    # Verify the result
                    assert result["repo"] == "owner/repo"
                    assert result["pr_number"] == 123
                    assert result["verdict"] == "needs_review"
                    assert result["pr_risk_level"] == "high"


def test_analyze_public_pr_with_token():
    """Test that public PR endpoint works with a GitHub token."""
    # Create a mock request
    mock_request = AnalyzeRequest(
        repo="owner/repo",
        pr_number=123,
        installation_id=None,
    )
    
    # Mock the settings to return a token
    with patch('api.user.urls.settings') as mock_settings:
        mock_settings.github_access_token = "ghp_test_token"
        mock_settings.llm_api_key = None
        mock_settings.ai_api_key = None
        mock_settings.llm_model = "test-model"
        mock_settings.llm_base_url = "https://test.com"
        
        # Mock build_public_github_client to verify it's called with the token
        with patch('api.user.urls.build_public_github_client') as mock_build_client:
            mock_source = Mock()
            mock_source.fetch_diff.return_value = Mock()  # Return a mock diff
            mock_build_client.return_value = mock_source
            
            # Mock PythonAdapter and CorePipeline
            with patch('api.user.urls.PythonAdapter') as mock_adapter_class:
                mock_language = Mock()
                mock_language.analyze.return_value = Mock()  # Return a mock semantic graph
                mock_adapter_class.return_value = mock_language
                
                with patch('api.user.urls.CorePipeline') as mock_pipeline_class:
                    mock_pipeline = Mock()
                    mock_reasoning_packet = ReasoningPacket(
                        summary="Test summary",
                        changed_areas=["area1"],
                        unresolved=[]
                    )
                    mock_pipeline.run.return_value = mock_reasoning_packet
                    mock_pipeline_class.return_value = mock_pipeline
                    
                    # Call the endpoint (it's async, so we need to run it)
                    result = asyncio.run(analyze_public_pr(body=mock_request))
                    
                    # Verify build_public_github_client was called with the token
                    mock_build_client.assert_called_once_with(token="ghp_test_token")
                    
                    # Verify the result
                    assert result["repo"] == "owner/repo"
                    assert result["pr_number"] == 123
                    assert result["verdict"] == "approved"
                    assert result["pr_risk_level"] == "low"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
