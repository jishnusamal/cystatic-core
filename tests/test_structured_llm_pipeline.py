"""Tests for the structured LLM → Jinja2 renderer architecture.

Tests the complete pipeline:
1. LLMContext models
2. GithubComment output models
3. Response parser
4. Jinja2 environment
5. GitHub comment renderer
6. GitHub comment generator orchestration
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from jinja2 import Template

from presentation.llm.models import (
    ExecutionSection,
    GithubComment,
    LLMContext,
    LLMDiscovery,
    LLMNarrative,
    LLMVisual,
    OperationalSection,
    SurprisingDiscovery,
    ValidationSection,
)
from presentation.llm.parser import LLMResponseParser
from presentation.render.environment import JinjaEnvironment
from presentation.render.github_comment_renderer import GithubCommentRenderer
from presentation.github_comment_generator import GithubCommentGenerator


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def sample_llm_context() -> LLMContext:
    """Create a sample LLMContext for testing."""
    return LLMContext(
        metadata={"repository": "test/repo", "language": "python"},
        summary={
            "changed_files": 5,
            "changed_symbols": 12,
            "affected_behaviors": 8,
            "execution_paths": 15,
            "services_reached": 3,
            "validation_gaps": 2,
            "surprising_discoveries": 1,
        },
        discoveries=(
            LLMDiscovery(
                id="reachable_units",
                kind="execution",
                title="Reachable Production Behaviors",
                summary="315 production behaviors depend on modified symbols",
                metrics={"execution_paths": 15, "reachable_units": 315, "depth": 5},
                surprise={"description": "Small change reaches many units", "max_ratio": 0.8},
                top_evidence=("auth.service.ts", "user.controller.ts"),
                narrative_position="opening",
            ),
        ),
        narrative=(
            LLMNarrative(
                section="execution_impact",
                order=1,
                description="Impact on execution chains",
                discovery_ids=("reachable_units",),
            ),
        ),
        visuals=(
            LLMVisual(
                discovery_id="reachable_units",
                semantic="reach",
                value=315,
                label="Reachable Units",
            ),
        ),
    )


@pytest.fixture
def sample_github_comment() -> GithubComment:
    """Create a sample GithubComment for testing."""
    return GithubComment(
        executive_summary="This change modifies authentication logic affecting 315 production behaviors across 15 execution paths.",
        review_priority="High - Core authentication changes with wide blast radius",
        biggest_surprise="A 2-line change reaches 315 units through shared authentication service",
        execution_summary="The modified symbols are called from 15 different execution paths, reaching 315 production behaviors with a maximum propagation depth of 5 levels.",
        operational_summary="No API or data model changes. The change is confined to authentication service internals.",
        validation_summary="2 validation gaps identified in authentication flow tests",
        attention="Focus review on authentication edge cases and error handling paths",
        surprising_discoveries=(
            SurprisingDiscovery(
                title="High Reach-to-Change Ratio",
                explanation="A small change in the authentication helper reaches 315 units through shared execution",
                metric="315 units / 2 lines = 157.5x reach",
                support="The auth.service.ts is imported by 12 different modules",
            ),
        ),
        execution=ExecutionSection(
            execution_paths=15,
            reachable_units=315,
            depth=5,
            narrative="Execution impact is concentrated in authentication flows",
            highlights=(
                SurprisingDiscovery(
                    title="Deep Propagation",
                    explanation="Change propagates through 5 levels of call stack",
                    metric="Depth: 5",
                ),
            ),
        ),
        operational=OperationalSection(
            api_count=0,
            data_count=0,
            event_count=0,
            dependency_count=0,
            narrative="No external contracts modified",
        ),
        validation=ValidationSection(
            summary="2 validation gaps in authentication flow test coverage",
        ),
        evidence=(
            "auth.service.ts modified",
            "user.controller.ts calls modified function",
            "12 modules import auth.service",
        ),
    )


@pytest.fixture
def sample_llm_json() -> str:
    """Create a sample LLM JSON response."""
    return json.dumps({
        "executive_summary": "This change modifies authentication logic affecting 315 production behaviors.",
        "review_priority": "High - Core authentication changes",
        "biggest_surprise": "A 2-line change reaches 315 units",
        "execution_summary": "Modified symbols are called from 15 execution paths",
        "operational_summary": "No API or data model changes",
        "validation_summary": "2 validation gaps identified",
        "attention": "Focus on authentication edge cases",
        "surprising_discoveries": [
            {
                "title": "High Reach-to-Change Ratio",
                "explanation": "Small change reaches many units",
                "metric": "315 units / 2 lines",
                "support": "auth.service.ts is imported by 12 modules",
            }
        ],
        "execution": {
            "execution_paths": 15,
            "reachable_units": 315,
            "depth": 5,
            "narrative": "Execution impact concentrated in auth flows",
            "highlights": [],
        },
        "operational": {
            "api_count": 0,
            "data_count": 0,
            "event_count": 0,
            "dependency_count": 0,
            "narrative": "No external contracts modified",
        },
        "validation": {
            "summary": "2 validation gaps in auth flow tests",
        },
        "evidence": [
            "auth.service.ts modified",
            "user.controller.ts calls modified function",
        ],
    })


# =========================================================================
# Model Tests
# =========================================================================


class TestLLMContext:
    """Tests for LLMContext model."""

    def test_create_llm_context(self, sample_llm_context: LLMContext) -> None:
        """Test creating an LLMContext."""
        assert sample_llm_context.metadata["repository"] == "test/repo"
        assert len(sample_llm_context.discoveries) == 1
        assert len(sample_llm_context.narrative) == 1
        assert len(sample_llm_context.visuals) == 1

    def test_llm_context_constraints(self) -> None:
        """Test that LLMContext has default constraints."""
        context = LLMContext(
            metadata={},
            summary={},
            discoveries=(),
            narrative=(),
            visuals=(),
        )
        assert len(context.constraints) == 5
        assert "Never invent new behaviors." in context.constraints

    def test_llm_context_normalizes_lists(self) -> None:
        """Test that LLMContext normalizes lists to tuples."""
        context = LLMContext(
            metadata={},
            summary={},
            discoveries=[],  # type: ignore
            narrative=[],
            visuals=[],
            constraints=[],
        )
        assert isinstance(context.discoveries, tuple)
        assert isinstance(context.narrative, tuple)
        assert isinstance(context.visuals, tuple)
        assert isinstance(context.constraints, tuple)


class TestGithubComment:
    """Tests for GithubComment model."""

    def test_create_github_comment(self, sample_github_comment: GithubComment) -> None:
        """Test creating a GithubComment."""
        assert sample_github_comment.executive_summary is not None
        assert len(sample_github_comment.executive_summary) > 0
        assert sample_github_comment.execution.execution_paths == 15
        assert sample_github_comment.operational.api_count == 0

    def test_github_comment_normalizes_nested_dicts(self) -> None:
        """Test that GithubComment normalizes dict inputs to models."""
        comment = GithubComment(
            executive_summary="Test",
            review_priority="High",
            biggest_surprise="None",
            execution_summary="Test",
            operational_summary="Test",
            validation_summary="Test",
            attention="Test",
            execution={"execution_paths": 10, "reachable_units": 50},  # type: ignore
            operational={"api_count": 2},  # type: ignore
            validation={"summary": "Test"},  # type: ignore
        )
        assert isinstance(comment.execution, ExecutionSection)
        assert isinstance(comment.operational, OperationalSection)
        assert isinstance(comment.validation, ValidationSection)
        assert comment.execution.execution_paths == 10
        assert comment.operational.api_count == 2

    def test_github_comment_normalizes_discovery_lists(self) -> None:
        """Test that GithubComment normalizes discovery lists."""
        comment = GithubComment(
            executive_summary="Test",
            review_priority="High",
            biggest_surprise="None",
            execution_summary="Test",
            operational_summary="Test",
            validation_summary="Test",
            attention="Test",
            surprising_discoveries=[  # type: ignore
                {"title": "Test", "explanation": "Test explanation"}
            ],
        )
        assert isinstance(comment.surprising_discoveries, tuple)
        assert len(comment.surprising_discoveries) == 1
        assert isinstance(comment.surprising_discoveries[0], SurprisingDiscovery)


# =========================================================================
# Parser Tests
# =========================================================================


class TestLLMResponseParser:
    """Tests for LLMResponseParser."""

    def test_parse_valid_json(self, sample_llm_json: str) -> None:
        """Test parsing valid JSON response."""
        parser = LLMResponseParser()
        comment = parser.parse(sample_llm_json)
        
        assert isinstance(comment, GithubComment)
        assert comment.executive_summary is not None
        assert comment.execution.execution_paths == 15

    def test_parse_json_in_markdown_block(self) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        json_data = {
            "executive_summary": "Test",
            "review_priority": "High",
            "biggest_surprise": "None",
            "execution_summary": "Test",
            "operational_summary": "Test",
            "validation_summary": "Test",
            "attention": "Test",
        }
        response = f"Here is the analysis:\n```json\n{json.dumps(json_data)}\n```\nHope this helps!"
        
        parser = LLMResponseParser()
        comment = parser.parse(response)
        assert comment.executive_summary == "Test"

    def test_parse_missing_required_field(self) -> None:
        """Test parsing fails with missing required field."""
        json_data = {
            "executive_summary": "Test",
            # Missing other required fields
        }
        
        parser = LLMResponseParser()
        with pytest.raises(ValueError, match="Missing required fields"):
            parser.parse(json.dumps(json_data))

    def test_parse_invalid_json(self) -> None:
        """Test parsing fails with invalid JSON."""
        parser = LLMResponseParser()
        with pytest.raises(ValueError, match="Invalid JSON"):
            parser.parse("not valid json {{{")

    def test_parse_string_truncation(self) -> None:
        """Test that long strings are truncated."""
        json_data = {
            "executive_summary": "x" * 600,  # Exceeds 500 char limit
            "review_priority": "High",
            "biggest_surprise": "None",
            "execution_summary": "Test",
            "operational_summary": "Test",
            "validation_summary": "Test",
            "attention": "Test",
        }
        
        parser = LLMResponseParser()
        comment = parser.parse(json.dumps(json_data))
        assert len(comment.executive_summary) <= 503  # 500 + "..."

    def test_parse_surprising_discoveries_limit(self) -> None:
        """Test that surprising_discoveries are limited to 5."""
        discoveries = [
            {"title": f"Discovery {i}", "explanation": "Test"}
            for i in range(10)
        ]
        json_data = {
            "executive_summary": "Test",
            "review_priority": "High",
            "biggest_surprise": "None",
            "execution_summary": "Test",
            "operational_summary": "Test",
            "validation_summary": "Test",
            "attention": "Test",
            "surprising_discoveries": discoveries,
        }
        
        parser = LLMResponseParser()
        comment = parser.parse(json.dumps(json_data))
        assert len(comment.surprising_discoveries) == 5

    def test_create_fallback_comment(self) -> None:
        """Test creating fallback comment on error."""
        parser = LLMResponseParser()
        error = RuntimeError("LLM failed")
        comment = parser.create_fallback_comment(error)
        
        assert isinstance(comment, GithubComment)
        assert "encountered an issue" in comment.executive_summary
        assert len(comment.evidence) > 0


# =========================================================================
# Jinja2 Environment Tests
# =========================================================================


class TestJinjaEnvironment:
    """Tests for Jinja2 environment."""

    def test_get_environment_singleton(self) -> None:
        """Test that get_environment returns singleton."""
        JinjaEnvironment.reset()
        env1 = JinjaEnvironment.get_environment()
        env2 = JinjaEnvironment.get_environment()
        assert env1 is env2

    def test_get_environment_creates_if_none(self) -> None:
        """Test that get_environment creates environment if not exists."""
        JinjaEnvironment.reset()
        env = JinjaEnvironment.get_environment()
        assert env is not None
        JinjaEnvironment.reset()

    def test_reset_environment(self) -> None:
        """Test resetting the environment."""
        JinjaEnvironment.reset()
        env1 = JinjaEnvironment.get_environment()
        JinjaEnvironment.reset()
        env2 = JinjaEnvironment.get_environment()
        # After reset, a new environment is created (different object)
        assert env1 is not env2


# =========================================================================
# Renderer Tests
# =========================================================================


class TestGithubCommentRenderer:
    """Tests for GithubCommentRenderer."""

    def test_render_comment(self, sample_github_comment: GithubComment) -> None:
        """Test rendering a GithubComment to markdown."""
        JinjaEnvironment.reset()
        renderer = GithubCommentRenderer()
        markdown = renderer.render(sample_github_comment)
        
        assert isinstance(markdown, str)
        assert len(markdown) > 0
        assert "Factor Engineering Discovery Report" in markdown
        assert "Executive Summary" in markdown
        assert "Execution Impact" in markdown

    def test_render_deterministic(self, sample_github_comment: GithubComment) -> None:
        """Test that rendering is deterministic."""
        JinjaEnvironment.reset()
        renderer = GithubCommentRenderer()
        markdown1 = renderer.render(sample_github_comment)
        markdown2 = renderer.render(sample_github_comment)
        assert markdown1 == markdown2

    def test_render_includes_metrics(self, sample_github_comment: GithubComment) -> None:
        """Test that rendered markdown includes metrics."""
        JinjaEnvironment.reset()
        renderer = GithubCommentRenderer()
        markdown = renderer.render(sample_github_comment)
        
        assert "315" in markdown  # reachable_units
        assert "15" in markdown   # execution_paths

    def test_render_includes_discoveries(self, sample_github_comment: GithubComment) -> None:
        """Test that rendered markdown includes discoveries."""
        JinjaEnvironment.reset()
        renderer = GithubCommentRenderer()
        markdown = renderer.render(sample_github_comment)
        
        assert "High Reach-to-Change Ratio" in markdown
        assert "157.5x" in markdown


# =========================================================================
# Integration Tests
# =========================================================================


class TestGithubCommentGenerator:
    """Tests for GithubCommentGenerator orchestration."""

    @patch('presentation.github_comment_generator.LLMClient')
    def test_generate_comment_success(
        self,
        mock_llm_client_class: MagicMock,
        sample_llm_context: LLMContext,
        sample_llm_json: str,
    ) -> None:
        """Test successful comment generation."""
        # Mock LLM client
        mock_client = MagicMock()
        mock_client.generate_structured_response.return_value = sample_llm_json
        mock_llm_client_class.return_value = mock_client
        
        # Mock context builder
        with patch('presentation.github_comment_generator.LLMContextBuilder') as mock_builder_class:
            mock_builder = MagicMock()
            mock_builder.build.return_value = sample_llm_context
            mock_builder_class.return_value = mock_builder
            
            # Create generator
            JinjaEnvironment.reset()
            generator = GithubCommentGenerator(
                api_key="test-key",
                model="test-model",
                repository="test/repo",
                pr_number="123",
                language="python",
            )
            
            # Mock presentation_ir
            mock_presentation_ir = MagicMock()
            
            # Generate comment
            markdown = generator.generate(mock_presentation_ir)
            
            assert isinstance(markdown, str)
            assert len(markdown) > 0
            assert "Factor Engineering Discovery Report" in markdown

    @patch('presentation.github_comment_generator.LLMClient')
    def test_generate_comment_with_llm_failure(
        self,
        mock_llm_client_class: MagicMock,
        sample_llm_context: LLMContext,
    ) -> None:
        """Test comment generation with LLM failure (fallback)."""
        # Mock LLM client to raise error
        mock_client = MagicMock()
        mock_client.generate_structured_response.side_effect = RuntimeError("LLM failed")
        mock_llm_client_class.return_value = mock_client
        
        # Mock context builder
        with patch('presentation.github_comment_generator.LLMContextBuilder') as mock_builder_class:
            mock_builder = MagicMock()
            mock_builder.build.return_value = sample_llm_context
            mock_builder_class.return_value = mock_builder
            
            # Create generator
            JinjaEnvironment.reset()
            generator = GithubCommentGenerator(
                api_key="test-key",
                model="test-model",
            )
            
            # Mock presentation_ir
            mock_presentation_ir = MagicMock()
            
            # Generate comment (should use fallback)
            markdown = generator.generate(mock_presentation_ir)
            
            assert isinstance(markdown, str)
            assert len(markdown) > 0
            # Fallback comment should still be valid markdown
            assert "Factor" in markdown


# =========================================================================
# End-to-End Pipeline Tests
# =========================================================================


class TestStructuredLLMPipeline:
    """End-to-end tests for the structured LLM pipeline."""

    def test_end_to_end_with_mock_llm(
        self,
        sample_llm_context: LLMContext,
        sample_llm_json: str,
    ) -> None:
        """Test complete pipeline: Context → Prompt → LLM JSON → Parser → Renderer."""
        # Step 1: Context is already built (sample_llm_context)
        
        # Step 2: Build prompts
        from presentation.llm.prompt_builder import PromptBuilder
        prompt_builder = PromptBuilder()
        system_prompt, user_prompt = prompt_builder.build_prompts(
            sample_llm_context,
            repository="test/repo",
            pr_number="123",
            language="python",
        )
        assert len(system_prompt) > 0
        assert len(user_prompt) > 0
        assert "JSON" in system_prompt
        
        # Step 3: Simulate LLM response (sample_llm_json)
        
        # Step 4: Parse JSON
        parser = LLMResponseParser()
        comment = parser.parse(sample_llm_json)
        assert isinstance(comment, GithubComment)
        
        # Step 5: Render to markdown
        JinjaEnvironment.reset()
        renderer = GithubCommentRenderer()
        markdown = renderer.render(comment)
        
        assert isinstance(markdown, str)
        assert len(markdown) > 0
        assert "Factor Engineering Discovery Report" in markdown
        assert "executive_summary content" in markdown.lower() or "authentication" in markdown.lower()

    def test_pipeline_rejects_markdown_from_llm(self) -> None:
        """Test that parser can handle LLM wrapping JSON in markdown."""
        json_data = {
            "executive_summary": "Test",
            "review_priority": "High",
            "biggest_surprise": "None",
            "execution_summary": "Test",
            "operational_summary": "Test",
            "validation_summary": "Test",
            "attention": "Test",
        }
        
        # LLM wraps in markdown code block
        response = f"```json\n{json.dumps(json_data)}\n```"
        
        parser = LLMResponseParser()
        comment = parser.parse(response)
        assert comment.executive_summary == "Test"

    def test_pipeline_validates_required_fields(self) -> None:
        """Test that parser validates all required fields."""
        incomplete_json = {
            "executive_summary": "Test",
            # Missing other required fields
        }
        
        parser = LLMResponseParser()
        with pytest.raises(ValueError, match="Missing required fields"):
            parser.parse(json.dumps(incomplete_json))