"""Tests for LLM Comment Generation Pipeline."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass, field

from presentation.llm.models import LLMContext, LLMDiscovery, LLMNarrative, LLMVisual
from presentation.llm.context_builder import LLMContextBuilder
from presentation.llm.prompt_builder import PromptBuilder
from presentation.llm.client import LLMClient
from presentation.llm.validator import CommentValidator, ValidatedComment
from presentation.renderers.github_comment_renderer import GitHubCommentRenderer
from presentation.publisher.github import GitHubPublisher


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def sample_presentation_ir():
    """Create a sample PresentationIR for testing."""
    from presentation.model import (
        PresentationIR,
        PresentationMetadata,
        PresentationSummary,
        PresentationDiscovery,
        PresentationEvidence,
        PresentationNarrative,
        PresentationVisual,
        DiscoveryKind,
        NarrativePosition,
        SignificanceMetrics,
        RankingVector,
        SurpriseVector,
        VisualSemantic,
    )
    
    metadata = PresentationMetadata(
        compiler_version="2.0.0",
        compiled_at="2026-07-17T20:00:00Z",
        discovery_count=3,
        evidence_count=10,
        pass_count=9,
    )
    
    summary = PresentationSummary(
        changed_files=5,
        changed_symbols=50,
        affected_behaviors=10,
        execution_paths=25,
        services_reached=3,
        validation_gaps=2,
        surprising_discoveries=1,
    )
    
    discoveries = []
    for i in range(3):
        evidence = tuple([
            PresentationEvidence(
                source=f"source_{i}",
                source_id=f"id_{i}",
                description=f"Evidence {i}",
                evidence_ref=f"ref_{i}",
            )
            for i in range(3)
        ])
        
        discovery = PresentationDiscovery(
            id=f"discovery_{i}",
            kind=DiscoveryKind.EXECUTION_SURFACE,
            title=f"Discovery {i}",
            summary=f"Summary for discovery {i}",
            evidence=evidence,
            metrics=SignificanceMetrics(
                execution_reach=10 + i,
                fan_out=5 + i,
                propagation_depth=3 + i,
            ),
            ranking_vector=RankingVector(
                has_external_surface=1,
                execution_reach=10 + i,
            ),
            surprise=SurpriseVector(
                max_ratio=5.0 + i,
                description=f"Surprising discovery {i}",
            ),
            visual_semantic=VisualSemantic.METRIC,
            narrative_position=NarrativePosition.IMPACT,
        )
        discoveries.append(discovery)
    
    narrative = [
        PresentationNarrative(
            section="summary",
            order=0,
            discovery_ids=("discovery_0",),
            description="Summary section",
        ),
        PresentationNarrative(
            section="impact",
            order=1,
            discovery_ids=("discovery_1", "discovery_2"),
            description="Impact section",
        ),
    ]
    
    visuals = [
        PresentationVisual(
            discovery_id="discovery_0",
            semantic=VisualSemantic.METRIC,
            value=10,
            label="Execution Reach",
        ),
    ]
    
    return PresentationIR(
        metadata=metadata,
        summary=summary,
        discoveries=tuple(discoveries),
        narrative=tuple(narrative),
        visuals=tuple(visuals),
        evidence=tuple(),
        navigation={},
    )


@pytest.fixture
def sample_llm_context():
    """Create a sample LLMContext for testing."""
    discoveries = tuple([
        LLMDiscovery(
            id=f"discovery_{i}",
            kind="execution_surface",
            title=f"Discovery {i}",
            summary=f"Summary for discovery {i}",
            metrics={"execution_reach": 10 + i, "fan_out": 5 + i},
            surprise={"max_ratio": 5.0 + i, "description": f"Surprising {i}"},
            top_evidence=tuple([f"evidence_{j}" for j in range(3)]),
            narrative_position="impact",
        )
        for i in range(3)
    ])
    
    narrative = tuple([
        LLMNarrative(
            section="summary",
            order=0,
            description="Summary section",
            discovery_ids=("discovery_0",),
        ),
    ])
    
    visuals = tuple([
        LLMVisual(
            discovery_id="discovery_0",
            semantic="metric",
            value=10,
            label="Execution Reach",
        ),
    ])
    
    return LLMContext(
        metadata={"compiler_version": "2.0.0", "discovery_count": 3},
        summary={"changed_files": 5, "changed_symbols": 50},
        discoveries=discoveries,
        narrative=narrative,
        visuals=visuals,
    )


# =========================================================================
# Test LLMContextBuilder
# =========================================================================


class TestLLMContextBuilder:
    """Test LLMContextBuilder."""
    
    def test_build_returns_llm_context(self, sample_presentation_ir):
        """Test that build returns LLMContext."""
        builder = LLMContextBuilder()
        result = builder.build(sample_presentation_ir)
        
        assert isinstance(result, LLMContext)
    
    def test_build_metadata(self, sample_presentation_ir):
        """Test that metadata is correctly built."""
        builder = LLMContextBuilder()
        result = builder.build(sample_presentation_ir)
        
        assert result.metadata["compiler_version"] == "2.0.0"
        assert result.metadata["discovery_count"] == 3
    
    def test_build_summary(self, sample_presentation_ir):
        """Test that summary is correctly built."""
        builder = LLMContextBuilder()
        result = builder.build(sample_presentation_ir)
        
        assert result.summary["changed_files"] == 5
        assert result.summary["changed_symbols"] == 50
    
    def test_build_discoveries(self, sample_presentation_ir):
        """Test that discoveries are correctly built."""
        builder = LLMContextBuilder()
        result = builder.build(sample_presentation_ir)
        
        assert len(result.discoveries) == 3
        assert all(isinstance(d, LLMDiscovery) for d in result.discoveries)
        assert result.discoveries[0].id == "discovery_0"
    
    def test_build_discoveries_evidence_limited(self, sample_presentation_ir):
        """Test that evidence is limited to 5 items per discovery."""
        builder = LLMContextBuilder()
        result = builder.build(sample_presentation_ir)
        
        # Each discovery has 3 evidence items in the fixture
        for discovery in result.discoveries:
            assert len(discovery.top_evidence) <= 5
    
    def test_build_narrative(self, sample_presentation_ir):
        """Test that narrative is correctly built."""
        builder = LLMContextBuilder()
        result = builder.build(sample_presentation_ir)
        
        assert len(result.narrative) == 2
        assert all(isinstance(n, LLMNarrative) for n in result.narrative)
    
    def test_build_visuals(self, sample_presentation_ir):
        """Test that visuals are correctly built."""
        builder = LLMContextBuilder()
        result = builder.build(sample_presentation_ir)
        
        assert len(result.visuals) == 1
        assert all(isinstance(v, LLMVisual) for v in result.visuals)
    
    def test_build_raises_on_none(self):
        """Test that build raises ValueError on None input."""
        builder = LLMContextBuilder()
        
        with pytest.raises(ValueError, match="presentation_ir is required"):
            builder.build(None)


# =========================================================================
# Test PromptBuilder
# =========================================================================


class TestPromptBuilder:
    """Test PromptBuilder."""
    
    def test_build_prompts_returns_tuple(self, sample_llm_context):
        """Test that build_prompts returns a tuple of two strings."""
        builder = PromptBuilder()
        system_prompt, user_prompt = builder.build_prompts(sample_llm_context)
        
        assert isinstance(system_prompt, str)
        assert isinstance(user_prompt, str)
        assert len(system_prompt) > 0
        assert len(user_prompt) > 0
    
    def test_system_prompt_contains_constraints(self, sample_llm_context):
        """Test that system prompt contains constraints."""
        builder = PromptBuilder()
        system_prompt, _ = builder.build_prompts(sample_llm_context)
        
        assert "Never invent" in system_prompt
        assert "compiler" in system_prompt.lower()
    
    def test_user_prompt_contains_summary(self, sample_llm_context):
        """Test that user prompt contains summary."""
        builder = PromptBuilder()
        _, user_prompt = builder.build_prompts(sample_llm_context)
        
        assert "Changed files" in user_prompt or "changed_files" in user_prompt
    
    def test_user_prompt_contains_discoveries(self, sample_llm_context):
        """Test that user prompt contains discoveries."""
        builder = PromptBuilder()
        _, user_prompt = builder.build_prompts(sample_llm_context)
        
        assert "Discovery" in user_prompt
    
    def test_build_prompts_with_metadata(self, sample_llm_context):
        """Test that prompts include repository and PR metadata."""
        builder = PromptBuilder()
        system_prompt, user_prompt = builder.build_prompts(
            sample_llm_context,
            repository="owner/repo",
            pr_number="123",
            language="python",
        )
        
        assert "owner/repo" in user_prompt
        assert "123" in user_prompt
        assert "python" in user_prompt


# =========================================================================
# Test LLMClient
# =========================================================================


class TestLLMClient:
    """Test LLMClient."""
    
    def test_init_with_api_key(self):
        """Test initialization with API key."""
        client = LLMClient(api_key="test-key")
        assert client.api_key == "test-key"
        # Model may be overridden by environment variable
        assert client.model is not None
        assert len(client.model) > 0
    
    def test_init_from_env(self, monkeypatch):
        """Test initialization from environment variable."""
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        client = LLMClient()
        assert client.api_key == "env-key"
    
    def test_init_raises_without_key(self, monkeypatch):
        """Test that initialization raises without API key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        with pytest.raises(ValueError, match="OpenAI API key required"):
            LLMClient()
    
    def test_get_model_info(self):
        """Test get_model_info returns configuration."""
        client = LLMClient(api_key="test-key")
        info = client.get_model_info()
        
        # Model may be overridden by environment variable
        assert info["model"] is not None
        assert len(info["model"]) > 0
        assert info["temperature"] == 0.3
        assert info["max_tokens"] == 2000
    
    def test_generate_comment(self):
        """Test generate_comment calls OpenAI API."""
        with patch("presentation.llm.client.OpenAI") as mock_openai_class:
            # Setup mock
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = "Generated comment"
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            
            # Test
            client = LLMClient(api_key="test-key")
            result = client.generate_comment("System prompt", "User prompt")
            
            assert result == "Generated comment"
            mock_client.chat.completions.create.assert_called_once()
    
    def test_generate_comment_raises_on_empty_response(self):
        """Test that generate_comment raises on empty response."""
        with patch("presentation.llm.client.OpenAI") as mock_openai_class:
            # Setup mock
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.choices = []
            mock_client.chat.completions.create.return_value = mock_response
            
            client = LLMClient(api_key="test-key")
            
            with pytest.raises(RuntimeError, match="OpenAI returned empty response"):
                client.generate_comment("System prompt", "User prompt")


# =========================================================================
# Test CommentValidator
# =========================================================================


class TestCommentValidator:
    """Test CommentValidator."""
    
    def test_validate_empty_comment(self):
        """Test validation of empty comment."""
        validator = CommentValidator()
        result = validator.validate("")
        
        assert result.is_valid is False
        assert "empty" in result.validation_errors[0].lower()
    
    def test_validate_valid_comment(self):
        """Test validation of valid comment."""
        validator = CommentValidator()
        comment = "# Test\n\nThis is a valid comment with headers.\n\n" + "x" * 100
        result = validator.validate(comment)
        
        assert result.is_valid is True
        assert len(result.validation_errors) == 0
    
    def test_validate_too_long_comment(self):
        """Test validation of too long comment."""
        validator = CommentValidator()
        comment = "# Test\n\n" + "x" * 10001
        result = validator.validate(comment)
        
        assert result.truncated is True
        # Account for truncation message that gets appended
        assert len(result.markdown) <= 10000 + len("\n\n*[Comment truncated due to length]*")
    
    def test_validate_too_short_comment(self):
        """Test validation of too short comment."""
        validator = CommentValidator()
        comment = "# Test"
        result = validator.validate(comment)
        
        assert result.is_valid is False
        assert any("too short" in err.lower() for err in result.validation_errors)
    
    def test_validate_no_headers(self):
        """Test validation of comment without headers."""
        validator = CommentValidator()
        comment = "This is a comment without any headers."
        result = validator.validate(comment)
        
        assert result.is_valid is False
        assert any("markdown structure" in err.lower() for err in result.validation_errors)
    
    def test_validate_returns_model_info(self):
        """Test that validation result includes model info."""
        validator = CommentValidator()
        result = validator.validate("# Test\n\nValid comment", model="gpt-4o")
        
        assert result.model == "gpt-4o"


# =========================================================================
# Test GitHubCommentRenderer
# =========================================================================


class TestGitHubCommentRenderer:
    """Test GitHubCommentRenderer."""
    
    def test_render_adds_footer(self, sample_llm_context):
        """Test that render adds metadata footer."""
        renderer = GitHubCommentRenderer()
        validated_comment = ValidatedComment(
            markdown="# Test\n\nComment",
            is_valid=True,
            model="gpt-4o",
        )
        
        result = renderer.render(validated_comment, sample_llm_context)
        
        assert "Generated by Factor" in result
        assert "gpt-4o" in result
    
    def test_render_fallback(self, sample_llm_context):
        """Test render_fallback generates deterministic comment."""
        renderer = GitHubCommentRenderer()
        result = renderer.render_fallback(sample_llm_context)
        
        assert "Factor Analysis Complete" in result
        assert "Changed Files" in result
        assert "5" in result  # From sample_llm_context
    
    def test_render_discovery_table(self):
        """Test render_discovery_table generates markdown table."""
        renderer = GitHubCommentRenderer()
        
        discoveries = (
            Mock(title="Discovery 1", kind="execution_surface", metrics={"execution_reach": 10}),
            Mock(title="Discovery 2", kind="api_surface", metrics={"execution_reach": 5}),
        )
        
        result = renderer.render_discovery_table(discoveries)
        
        assert "|" in result
        assert "Discovery 1" in result
        assert "Discovery 2" in result
    
    def test_render_metrics_table(self):
        """Test render_metrics_table generates markdown table."""
        renderer = GitHubCommentRenderer()
        
        metrics = {"execution_reach": 10, "fan_out": 5}
        result = renderer.render_metrics_table(metrics)
        
        assert "|" in result
        assert "execution_reach" in result
        assert "10" in result


# =========================================================================
# Test GitHubPublisher
# =========================================================================


class TestGitHubPublisher:
    """Test GitHubPublisher."""
    
    def test_init(self):
        """Test initialization."""
        publisher = GitHubPublisher(token="test-token")
        assert publisher.token == "test-token"
    
    @pytest.mark.asyncio
    async def test_publish_comment_success(self):
        """Test successful comment publishing."""
        with patch("presentation.publisher.github.GitHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": 12345}
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            
            publisher = GitHubPublisher(token="test-token")
            result = await publisher.publish_comment(
                repository="owner/repo",
                pr_number=1,
                markdown="# Test Comment",
            )
            
            assert result["success"] is True
            assert result["comment_id"] == "12345"
            assert result["error"] is None
    
    @pytest.mark.asyncio
    async def test_publish_comment_failure(self):
        """Test comment publishing failure."""
        with patch("presentation.publisher.github.GitHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_client.post.side_effect = Exception("API error")
            
            publisher = GitHubPublisher(token="test-token")
            result = await publisher.publish_comment(
                repository="owner/repo",
                pr_number=1,
                markdown="# Test Comment",
            )
            
            assert result["success"] is False
            assert result["comment_id"] is None
            assert "API error" in result["error"]
    
    def test_publish_comment_sync(self):
        """Test synchronous comment publishing."""
        with patch("presentation.publisher.github.GitHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": 12345}
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response
            
            publisher = GitHubPublisher(token="test-token")
            result = publisher.publish_comment_sync(
                repository="owner/repo",
                pr_number=1,
                markdown="# Test Comment",
            )
            
            assert result["success"] is True
            assert result["comment_id"] == "12345"
