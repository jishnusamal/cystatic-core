"""Integration tests for the runtime pipeline."""

from __future__ import annotations

import pytest

from core.errors import LanguageDetectionFailed, LanguageNotSupported
from engine.language.detection import LanguageAdapterFactory
from engine.pipeline.pipeline import PipelineContext
from integrations.github.renderers.json_renderer import JSONRenderer
from integrations.github.renderers.github_renderer import GitHubRenderer
from engine.repository.indexing import MemoryRepositoryStore


class TestLanguageDetection:
    """Tests for language detection."""
    
    def test_detect_python_files(self):
        """Test detection of Python files."""
        factory = LanguageAdapterFactory()
        files = {
            "main.py": "print('hello')",
            "utils.py": "def helper(): pass",
            "app.py": "from flask import Flask",
        }
        
        language = factory.detect_language(files)
        assert language == "python"
    
    def test_detect_java_files(self):
        """Test detection of Java files."""
        factory = LanguageAdapterFactory()
        files = {
            "Main.java": "public class Main {}",
            "Utils.java": "public class Utils {}",
        }
        
        language = factory.detect_language(files)
        assert language == "java"
    
    def test_detect_mixed_files(self):
        """Test detection with mixed file types."""
        factory = LanguageAdapterFactory()
        files = {
            "main.py": "print('hello')",
            "Main.java": "public class Main {}",
        }
        
        # Should detect Python first (higher priority)
        language = factory.detect_language(files)
        assert language == "python"
    
    def test_detect_no_files(self):
        """Test detection with no files."""
        factory = LanguageAdapterFactory()
        
        with pytest.raises(LanguageDetectionFailed):
            factory.detect_language({})
    
    def test_create_adapter_python(self):
        """Test creating Python adapter."""
        factory = LanguageAdapterFactory()
        adapter = factory.create_adapter("python")
        
        assert adapter.get_language() == "python"
    
    def test_create_adapter_unsupported(self):
        """Test creating adapter for unsupported language."""
        factory = LanguageAdapterFactory()
        
        with pytest.raises(LanguageNotSupported):
            factory.create_adapter("rust")
    
    def test_detect_and_create(self):
        """Test detect and create in one step."""
        factory = LanguageAdapterFactory()
        files = {"main.py": "print('hello')"}
        
        language, adapter = factory.detect_and_create(files)
        assert language == "python"
        assert adapter.get_language() == "python"


class TestPipelineContext:
    """Tests for pipeline context."""
    
    def test_create_context(self):
        """Test creating a pipeline context."""
        context = PipelineContext(repository="owner/repo")
        
        assert context.repository == "owner/repo"
        assert context.base_sha is None
        assert context.head_sha is None
        assert context.ocm is None
        assert context.error is None
    
    def test_context_timing(self):
        """Test context timing methods."""
        context = PipelineContext(repository="owner/repo")
        
        context.mark_compilation_start()
        import time
        time.sleep(0.01)  # Small delay to ensure time difference
        
        context.mark_repository_compiled()
        assert context.repository_compile_time is not None
        assert context.repository_compile_time > 0
        
        context.mark_complete()
        assert context.total_time is not None
        assert context.total_time > 0
    
    def test_context_to_dict(self):
        """Test converting context to dictionary."""
        context = PipelineContext(
            repository="owner/repo",
            base_sha="abc123",
            head_sha="def456",
            language="python",
        )
        
        data = context.to_dict()
        assert data["repository"] == "owner/repo"
        assert data["base_sha"] == "abc123"
        assert data["head_sha"] == "def456"
        assert data["language"] == "python"
        assert data["has_error"] is False


class TestMemoryRepositoryStore:
    """Tests for memory repository store."""
    
    @pytest.mark.asyncio
    async def test_save_and_load(self):
        """Test saving and loading a model."""
        from engine.language.model import RepositoryModel
        from engine.language.model.graphs import CallGraph, ReferenceGraph, TypeRelationshipGraph
        
        store = MemoryRepositoryStore()
        model = RepositoryModel(
            symbols=frozenset(),
            call_graph=CallGraph(),
            reference_graph=ReferenceGraph(),
            type_relationship_graph=TypeRelationshipGraph(),
            metadata={"root_path": "/tmp/test", "language": "python"},
        )
        
        await store.save("owner/repo", "main", model)
        loaded = await store.load("owner/repo", "main")
        
        assert loaded is not None
        assert loaded.metadata.get("language") == "python"
        assert loaded.metadata.get("root_path") == "/tmp/test"
    
    @pytest.mark.asyncio
    async def test_load_nonexistent(self):
        """Test loading a non-existent model."""
        store = MemoryRepositoryStore()
        
        loaded = await store.load("owner/repo", "main")
        assert loaded is None
    
    @pytest.mark.asyncio
    async def test_exists(self):
        """Test checking if a model exists."""
        from engine.language.model import RepositoryModel
        from engine.language.model.graphs import CallGraph, ReferenceGraph, TypeRelationshipGraph
        
        store = MemoryRepositoryStore()
        model = RepositoryModel(
            symbols=frozenset(),
            call_graph=CallGraph(),
            reference_graph=ReferenceGraph(),
            type_relationship_graph=TypeRelationshipGraph(),
        )
        
        assert not await store.exists("owner/repo", "main")
        
        await store.save("owner/repo", "main", model)
        assert await store.exists("owner/repo", "main")
    
    @pytest.mark.asyncio
    async def test_invalidate(self):
        """Test invalidating a cached model."""
        from engine.language.model import RepositoryModel
        from engine.language.model.graphs import CallGraph, ReferenceGraph, TypeRelationshipGraph
        
        store = MemoryRepositoryStore()
        model = RepositoryModel(
            symbols=frozenset(),
            call_graph=CallGraph(),
            reference_graph=ReferenceGraph(),
            type_relationship_graph=TypeRelationshipGraph(),
        )
        
        await store.save("owner/repo", "main", model)
        assert await store.exists("owner/repo", "main")
        
        await store.invalidate("owner/repo", "main")
        assert not await store.exists("owner/repo", "main")
    
    @pytest.mark.asyncio
    async def test_invalidate_all(self):
        """Test invalidating all refs for a repository."""
        from engine.language.model import RepositoryModel
        from engine.language.model.graphs import CallGraph, ReferenceGraph, TypeRelationshipGraph
        
        store = MemoryRepositoryStore()
        model = RepositoryModel(
            symbols=frozenset(),
            call_graph=CallGraph(),
            reference_graph=ReferenceGraph(),
            type_relationship_graph=TypeRelationshipGraph(),
        )
        
        await store.save("owner/repo", "main", model)
        await store.save("owner/repo", "develop", model)
        
        assert await store.exists("owner/repo", "main")
        assert await store.exists("owner/repo", "develop")
        
        await store.invalidate("owner/repo")
        
        assert not await store.exists("owner/repo", "main")
        assert not await store.exists("owner/repo", "develop")


class TestJSONRenderer:
    """Tests for JSON renderer."""
    
    def test_render_empty_models(self):
        """Test rendering with minimal models."""
        from engine.language.model import RepositoryModel
        from engine.language.model.graphs import CallGraph, ReferenceGraph, TypeRelationshipGraph
        from engine.change.model import ChangeModel
        from engine.behavior.model import BehaviorModel
        from engine.operational.model import OperationalChangeModel
        
        repository = RepositoryModel(
            symbols=frozenset(),
            call_graph=CallGraph(),
            reference_graph=ReferenceGraph(),
            type_relationship_graph=TypeRelationshipGraph(),
            metadata={"root_path": "/tmp/test", "language": "python"},
        )
        
        change = ChangeModel(
            added_symbols=[],
            removed_symbols=[],
            modified_symbols=[],
            changed_imports=[],
            changed_endpoints=[],
        )
        
        behavior = BehaviorModel(
            behaviors=[],
            execution_graphs=[],
        )
        
        ocm = OperationalChangeModel(
            repository=repository,
            change=change,
            behavior=behavior,
        )
        
        renderer = JSONRenderer()
        result = renderer.render(ocm)
        
        assert "repository" in result
        assert "change" in result
        assert "behavior" in result
        assert result["repository"]["language"] == "python"
        assert result["change"]["added_symbols_count"] == 0


class TestGitHubRenderer:
    """Tests for GitHub renderer."""
    
    def test_render_simple(self):
        """Test rendering a simple summary."""
        from engine.language.model import RepositoryModel, Symbol, SymbolKind
        from engine.change.model import ChangeModel, ModifiedSymbol
        from engine.behavior.model import BehaviorModel
        from engine.operational.model import OperationalChangeModel
        
        from engine.language.model import RepositoryModel
        from engine.language.model.graphs import CallGraph, ReferenceGraph, TypeRelationshipGraph
        
        repository = RepositoryModel(
            symbols=frozenset(),
            call_graph=CallGraph(),
            reference_graph=ReferenceGraph(),
            type_relationship_graph=TypeRelationshipGraph(),
            metadata={"root_path": "/tmp/test", "language": "python"},
        )
        
        symbol = Symbol(
            id="test:main.py:function:helper",
            name="helper",
            kind=SymbolKind.FUNCTION,
            language="python",
            file="main.py",
            range=(1, 1),
        )
        
        change = ChangeModel(
            added_symbols=[],
            removed_symbols=[],
            modified_symbols=[
                ModifiedSymbol(
                    symbol=symbol,
                    changes=[],
                )
            ],
            changed_imports=[],
            changed_endpoints=[],
        )
        
        behavior = BehaviorModel(
            behaviors=[],
            execution_graphs=[],
        )
        
        ocm = OperationalChangeModel(
            repository=repository,
            change=change,
            behavior=behavior,
        )
        
        renderer = GitHubRenderer()
        result = renderer.render_simple(ocm)
        
        assert "# Cystatic Analysis" in result
        assert "python" in result
        assert "Modified:** 1 symbols" in result


class TestPipelineTokenCount:
    """Tests for pipeline LLMContext token counting."""
    
    def test_calculate_llm_context_tokens(self):
        """Test calculating token counts for LLMContext elements."""
        from engine.pipeline.pipeline import Pipeline
        pipeline = Pipeline()
        
        test_context = {
            "st": ["", "file.py", "func"],
            "f": [[1, 2]],
            "sym": [[0, 1, 2]],
            "ep": [[2, 1]],
            "cs": [1, 2, 3, 4, 5],
            "cf": [],
            "eg": {"n": [], "e": []},
            "epts": [],
            "disc": []
        }
        
        token_counts = pipeline.calculate_llm_context_tokens(test_context)
        assert token_counts is not None
        assert "total" in token_counts
        assert token_counts["st"] > 0
        assert token_counts["f"] > 0
        assert token_counts["sym"] > 0
        assert token_counts["total"] >= sum(token_counts[k] for k in test_context.keys())
    
    def test_calculate_llm_context_tokens_empty(self):
        """Test calculating token counts for empty context."""
        from engine.pipeline.pipeline import Pipeline
        pipeline = Pipeline()
        
        assert pipeline.calculate_llm_context_tokens({}) is None

    def test_compress_llm_context(self):
        """Test compressing LLMContext elements using compress_llm_context."""
        from engine.pipeline.pipeline import Pipeline
        pipeline = Pipeline()
        
        test_context = {
            "st": ["short", "this is a very long string table entry that can potentially be compressed by llmlingua"],
            "disc": [[1, ["another very long string fact that contains detailed contextual information for compression"]]]
        }
        
        compressed = pipeline.compress_llm_context(test_context)
        assert compressed is not None
        assert "st" in compressed
        assert "disc" in compressed
        assert pipeline.compress_llm_context({}) is None


