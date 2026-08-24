"""Tests for the Change Compiler."""

from dataclasses import dataclass

import pytest
from engine.language.model import (
    CallGraph,
    ReferenceGraph,
    RepositoryModel,
    Symbol,
    SymbolKind,
    SymbolVisibility,
)

from engine.change.compiler import ChangeCompiler
from engine.change.compiler.passes import (
    ChangeClassificationPass,
    ChangedSymbolsPass,
    FileClassificationPass,
)
from engine.change.compiler.passes.base import ChangePassContext
from engine.change.model import (
    DecoratorChange,
    SignatureChange,
    VisibilityChange,
)
from engine.change.model.repository_comparison import RepositoryComparison
from engine.change.passes.file_classification import FileKind


@dataclass(frozen=True)
class TestHelper:
    """Helper to create test symbols."""

    @staticmethod
    def create_symbol(
        symbol_id: str,
        name: str,
        kind: SymbolKind,
        file: str = "test.py",
        start_line: int = 1,
        end_line: int = 10,
        visibility: SymbolVisibility = SymbolVisibility.PUBLIC,
        properties: dict | None = None,
    ) -> Symbol:
        """Create a test symbol."""
        return Symbol(
            id=symbol_id,
            name=name,
            kind=kind,
            language="python",
            file=file,
            range=(start_line, end_line),
            visibility=visibility,
            properties=properties or {},
        )

    @staticmethod
    def create_repository_model(symbols: list[Symbol]) -> RepositoryModel:
        """Create a test repository model."""
        return RepositoryModel(
            symbols=frozenset(symbols),
            call_graph=CallGraph(edges=()),
            reference_graph=ReferenceGraph(edges=()),
            entry_points=(),
        )


class TestChangeCompiler:
    """Test suite for ChangeCompiler."""

    def test_empty_change(self):
        """Test compiling with no changes."""
        compiler = ChangeCompiler()

        # Create identical old and new models
        symbol = TestHelper.create_symbol(
            "python://test.py::func1", "func1", SymbolKind.FUNCTION
        )
        old_model = TestHelper.create_repository_model([symbol])
        new_model = TestHelper.create_repository_model([symbol])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        assert len(result.added_symbols) == 0
        assert len(result.removed_symbols) == 0
        assert len(result.modified_symbols) == 0
        assert len(result.changed_imports) == 0
        assert len(result.changed_endpoints) == 0

    def test_added_symbol(self):
        """Test detecting added symbols."""
        compiler = ChangeCompiler()

        old_symbol = TestHelper.create_symbol(
            "python://test.py::func1", "func1", SymbolKind.FUNCTION
        )
        new_symbol1 = TestHelper.create_symbol(
            "python://test.py::func1", "func1", SymbolKind.FUNCTION
        )
        new_symbol2 = TestHelper.create_symbol(
            "python://test.py::func2", "func2", SymbolKind.FUNCTION
        )

        old_model = TestHelper.create_repository_model([old_symbol])
        new_model = TestHelper.create_repository_model([new_symbol1, new_symbol2])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        assert len(result.added_symbols) == 1
        added_ids = {s.id for s in result.added_symbols}
        assert "python://test.py::func2" in added_ids
        assert len(result.removed_symbols) == 0
        assert len(result.modified_symbols) == 0

    def test_removed_symbol(self):
        """Test detecting removed symbols."""
        compiler = ChangeCompiler()

        old_symbol1 = TestHelper.create_symbol(
            "python://test.py::func1", "func1", SymbolKind.FUNCTION
        )
        old_symbol2 = TestHelper.create_symbol(
            "python://test.py::func2", "func2", SymbolKind.FUNCTION
        )
        new_symbol = TestHelper.create_symbol(
            "python://test.py::func1", "func1", SymbolKind.FUNCTION
        )

        old_model = TestHelper.create_repository_model([old_symbol1, old_symbol2])
        new_model = TestHelper.create_repository_model([new_symbol])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        assert len(result.added_symbols) == 0
        assert len(result.removed_symbols) == 1
        removed_ids = {s.id for s in result.removed_symbols}
        assert "python://test.py::func2" in removed_ids
        assert len(result.modified_symbols) == 0

    def test_modified_symbol_range(self):
        """Test detecting modified symbols (range change)."""
        compiler = ChangeCompiler()

        old_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            start_line=1,
            end_line=10,
        )
        new_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            start_line=1,
            end_line=15,
        )

        old_model = TestHelper.create_repository_model([old_symbol])
        new_model = TestHelper.create_repository_model([new_symbol])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        assert len(result.added_symbols) == 0
        assert len(result.removed_symbols) == 0
        assert len(result.modified_symbols) == 1
        assert result.modified_symbols[0].symbol.id == "python://test.py::func1"

    def test_modified_symbol_visibility(self):
        """Test detecting visibility changes."""
        compiler = ChangeCompiler()

        old_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            visibility=SymbolVisibility.PRIVATE,
        )
        new_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            visibility=SymbolVisibility.PUBLIC,
        )

        old_model = TestHelper.create_repository_model([old_symbol])
        new_model = TestHelper.create_repository_model([new_symbol])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        assert len(result.modified_symbols) == 1
        modified = result.modified_symbols[0]

        # Should have visibility change
        visibility_changes = [
            c for c in modified.changes if isinstance(c, VisibilityChange)
        ]
        assert len(visibility_changes) == 1
        assert visibility_changes[0].old_visibility == "private"
        assert visibility_changes[0].new_visibility == "public"

    def test_modified_symbol_signature(self):
        """Test detecting signature changes."""
        compiler = ChangeCompiler()

        old_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            properties={"signature": "func1(a, b)"},
        )
        new_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            properties={"signature": "func1(a, b, c)"},
        )

        old_model = TestHelper.create_repository_model([old_symbol])
        new_model = TestHelper.create_repository_model([new_symbol])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        assert len(result.modified_symbols) == 1
        modified = result.modified_symbols[0]

        # Should have signature change
        signature_changes = [
            c for c in modified.changes if isinstance(c, SignatureChange)
        ]
        assert len(signature_changes) == 1
        assert signature_changes[0].old_signature == "func1(a, b)"
        assert signature_changes[0].new_signature == "func1(a, b, c)"

    def test_modified_symbol_decorators(self):
        """Test detecting decorator changes."""
        compiler = ChangeCompiler()

        old_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            properties={"decorators": ["@staticmethod"]},
        )
        new_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            properties={"decorators": ["@classmethod"]},
        )

        old_model = TestHelper.create_repository_model([old_symbol])
        new_model = TestHelper.create_repository_model([new_symbol])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        assert len(result.modified_symbols) == 1
        modified = result.modified_symbols[0]

        # Should have decorator change
        decorator_changes = [
            c for c in modified.changes if isinstance(c, DecoratorChange)
        ]
        assert len(decorator_changes) == 1
        assert decorator_changes[0].old_decorators == ("@staticmethod",)
        assert decorator_changes[0].new_decorators == ("@classmethod",)

    def test_changed_imports(self):
        """Test detecting changed imports."""
        compiler = ChangeCompiler()

        old_import = TestHelper.create_symbol(
            "python://test.py::import os",
            "os",
            SymbolKind.IMPORT,
            properties={"module": "os"},
        )
        new_import = TestHelper.create_symbol(
            "python://test.py::import sys",
            "sys",
            SymbolKind.IMPORT,
            properties={"module": "sys"},
        )

        old_model = TestHelper.create_repository_model([old_import])
        new_model = TestHelper.create_repository_model([new_import])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        # Different import names create different symbol IDs, so they appear as added/removed
        assert len(result.added_symbols) == 1
        assert len(result.removed_symbols) == 1
        assert len(result.changed_imports) == 2  # One added, one removed

        # Verify the import changes
        change_types = {c.change_type for c in result.changed_imports}
        assert "added" in change_types
        assert "removed" in change_types

    def test_changed_endpoints(self):
        """Test detecting changed endpoints."""
        compiler = ChangeCompiler()

        old_endpoint = TestHelper.create_symbol(
            "python://test.py::get_user",
            "get_user",
            SymbolKind.FUNCTION,
            properties={"endpoint": "/users", "http_method": "GET"},
        )
        new_endpoint = TestHelper.create_symbol(
            "python://test.py::get_user",
            "get_user",
            SymbolKind.FUNCTION,
            properties={"endpoint": "/users/{id}", "http_method": "GET"},
        )

        old_model = TestHelper.create_repository_model([old_endpoint])
        new_model = TestHelper.create_repository_model([new_endpoint])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        assert len(result.changed_endpoints) == 1
        assert result.changed_endpoints[0].symbol_id == "python://test.py::get_user"
        assert result.changed_endpoints[0].old_endpoint == "/users"
        assert result.changed_endpoints[0].new_endpoint == "/users/{id}"
        assert result.changed_endpoints[0].change_type == "modified"

    def test_complex_change(self):
        """Test a complex change with multiple types of modifications."""
        compiler = ChangeCompiler()

        # Old symbols
        old_func = TestHelper.create_symbol(
            "python://test.py::calculate",
            "calculate",
            SymbolKind.FUNCTION,
            start_line=1,
            end_line=10,
            visibility=SymbolVisibility.PRIVATE,
            properties={
                "signature": "calculate(a, b)",
                "decorators": ["@staticmethod"],
            },
        )
        old_import = TestHelper.create_symbol(
            "python://test.py::import math",
            "math",
            SymbolKind.IMPORT,
            properties={"module": "math"},
        )

        # New symbols
        new_func = TestHelper.create_symbol(
            "python://test.py::calculate",
            "calculate",
            SymbolKind.FUNCTION,
            start_line=1,
            end_line=15,  # Range changed
            visibility=SymbolVisibility.PUBLIC,  # Visibility changed
            properties={
                "signature": "calculate(a, b, c)",  # Signature changed
                "decorators": ["@classmethod"],  # Decorators changed
            },
        )
        new_import = TestHelper.create_symbol(
            "python://test.py::import numpy",
            "numpy",
            SymbolKind.IMPORT,
            properties={"module": "numpy"},
        )

        old_model = TestHelper.create_repository_model([old_func, old_import])
        new_model = TestHelper.create_repository_model([new_func, new_import])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        # Check modified symbol
        assert len(result.modified_symbols) == 1
        modified = result.modified_symbols[0]
        assert modified.symbol.id == "python://test.py::calculate"

        # Should have multiple change types
        change_types = [type(c).__name__ for c in modified.changes]
        assert "FunctionBodyChange" in change_types
        assert "SignatureChange" in change_types
        assert "VisibilityChange" in change_types
        assert "DecoratorChange" in change_types

        # Check changed imports (different names = added + removed)
        assert len(result.added_symbols) == 1
        assert len(result.removed_symbols) == 1
        assert len(result.changed_imports) == 2  # One added, one removed

    def test_get_added_symbols_by_kind(self):
        """Test filtering added symbols by kind."""
        compiler = ChangeCompiler()

        old_func = TestHelper.create_symbol(
            "python://test.py::func1", "func1", SymbolKind.FUNCTION
        )
        new_func = TestHelper.create_symbol(
            "python://test.py::func1", "func1", SymbolKind.FUNCTION
        )
        new_class = TestHelper.create_symbol(
            "python://test.py::MyClass", "MyClass", SymbolKind.CLASS
        )

        old_model = TestHelper.create_repository_model([old_func])
        new_model = TestHelper.create_repository_model([new_func, new_class])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        added_classes = result.get_added_symbols_by_kind("class")
        assert len(added_classes) == 1
        added_class_ids = {s.id for s in added_classes}
        assert "python://test.py::MyClass" in added_class_ids

    def test_get_changes_for_symbol(self):
        """Test getting changes for a specific symbol."""
        compiler = ChangeCompiler()

        old_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            start_line=1,
            end_line=10,
        )
        new_symbol = TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
            start_line=1,
            end_line=15,
        )

        old_model = TestHelper.create_repository_model([old_symbol])
        new_model = TestHelper.create_repository_model([new_symbol])

        comparison = RepositoryComparison(
            base_model=old_model,
            head_model=new_model,
            diff={},
            base_sha="abc123",
            head_sha="def456",
        )

        result = compiler.compile(comparison)

        modified = result.get_changes_for_symbol("python://test.py::func1")
        assert modified is not None
        assert modified.symbol.id == "python://test.py::func1"
        assert len(modified.changes) > 0

        # Non-existent symbol should return None
        assert result.get_changes_for_symbol("python://test.py::nonexistent") is None


def _ts_symbol(
    symbol_id: str,
    name: str,
    kind: SymbolKind,
    file: str,
    start_line: int = 1,
    end_line: int = 5,
) -> Symbol:
    return Symbol(
        id=symbol_id,
        name=name,
        kind=kind,
        language="typescript",
        file=file,
        range=(start_line, end_line),
        visibility=SymbolVisibility.PUBLIC,
        properties={},
    )


class TestFileClassificationIntegration:
    """Frontend TS/TSX must be excluded before semantic change analysis."""

    def _compile_models(self, old_symbols, new_symbols):
        compiler = ChangeCompiler()
        result = compiler.compile(
            RepositoryComparison(
                base_model=TestHelper.create_repository_model(old_symbols),
                head_model=TestHelper.create_repository_model(new_symbols),
                diff={},
                base_sha="abc123",
                head_sha="def456",
            )
        )
        return compiler, result

    def test_pass_chain_order(self):
        compiler = ChangeCompiler()
        names = [p.name for p in compiler.passes]
        assert names == ["file_classification", "changed_symbols", "change_classification"]
        assert isinstance(compiler.passes[0], FileClassificationPass)
        assert isinstance(compiler.passes[1], ChangedSymbolsPass)
        assert isinstance(compiler.passes[2], ChangeClassificationPass)

    def test_frontend_tsx_included_in_analysis(self):
        old_btn = _ts_symbol(
            "ts://frontend/Button.tsx::Button",
            "Button",
            SymbolKind.CLASS,
            "frontend/Button.tsx",
        )
        new_btn = _ts_symbol(
            "ts://frontend/Button.tsx::Button",
            "Button",
            SymbolKind.CLASS,
            "frontend/Button.tsx",
            end_line=20,
        )

        compiler, result = self._compile_models([old_btn], [new_btn])

        # Frontend TSX is now included in analysis
        assert len(result.modified_symbols) == 1
        assert result.modified_symbols[0].symbol.file == "frontend/Button.tsx"
        assert compiler.last_excluded_files == frozenset()
        assert (
            compiler.last_file_classifications["frontend/Button.tsx"].kind
            == FileKind.FRONTEND
        )

    def test_backend_ts_continues_through_analysis(self):
        old_api = _ts_symbol(
            "ts://server/api.ts::handler", "handler", SymbolKind.FUNCTION, "server/api.ts"
        )
        new_api = _ts_symbol(
            "ts://server/api.ts::handler",
            "handler",
            SymbolKind.FUNCTION,
            "server/api.ts",
            end_line=15,
        )
        new_helper = _ts_symbol(
            "ts://server/api.ts::helper", "helper", SymbolKind.FUNCTION, "server/api.ts"
        )

        compiler, result = self._compile_models([old_api], [new_api, new_helper])

        modified_files = {m.symbol.file for m in result.modified_symbols}
        added_files = {s.file for s in result.added_symbols}
        assert "server/api.ts" in modified_files or "server/api.ts" in added_files
        assert compiler.last_excluded_files == frozenset()

    def test_shared_ts_continues_through_analysis(self):
        old_types = _ts_symbol(
            "ts://shared/types.ts::User",
            "User",
            SymbolKind.CLASS,
            "shared/types.ts",
        )
        new_types = _ts_symbol(
            "ts://shared/types.ts::User",
            "User",
            SymbolKind.CLASS,
            "shared/types.ts",
            end_line=30,
        )

        compiler, result = self._compile_models([old_types], [new_types])

        assert len(result.modified_symbols) == 1
        assert result.modified_symbols[0].symbol.file == "shared/types.ts"
        assert compiler.last_excluded_files == frozenset()

    @pytest.mark.parametrize(
        "path,sid",
        [
            ("backend/api.ts", "ts://backend/api.ts::handler"),
            ("shared/types.ts", "ts://shared/types.ts::User"),
            ("python/service.py", "python://python/service.py::run"),
            ("java/Service.java", "java://java/Service.java::Service"),
        ],
    )
    def test_regression_eligible_roles_unchanged(self, path, sid):
        name = sid.split("::")[-1]
        kind = SymbolKind.CLASS if name[0].isupper() else SymbolKind.FUNCTION
        old_sym = _ts_symbol(sid, name, kind, path)
        new_sym = _ts_symbol(sid, name, kind, path, end_line=42)

        compiler, result = self._compile_models([old_sym], [new_sym])

        assert len(result.modified_symbols) == 1
        assert result.modified_symbols[0].symbol.id == sid
        assert path not in compiler.last_excluded_files

    def test_mixed_change_set_partitions_correctly(self):
        old_btn = _ts_symbol(
            "ts://src/components/Button.tsx::Button",
            "Button",
            SymbolKind.CLASS,
            "src/components/Button.tsx",
        )
        new_btn = _ts_symbol(
            "ts://src/components/Button.tsx::Button",
            "Button",
            SymbolKind.CLASS,
            "src/components/Button.tsx",
            end_line=99,
        )
        old_api = _ts_symbol(
            "ts://workers/process.ts::process",
            "process",
            SymbolKind.FUNCTION,
            "workers/process.ts",
        )
        new_api = _ts_symbol(
            "ts://workers/process.ts::process",
            "process",
            SymbolKind.FUNCTION,
            "workers/process.ts",
            end_line=50,
        )

        compiler, result = self._compile_models([old_btn, old_api], [new_btn, new_api])

        analyzed_files = {m.symbol.file for m in result.modified_symbols}
        assert analyzed_files == {"workers/process.ts", "src/components/Button.tsx"}
        assert result.files_changed == 2
        assert compiler.last_excluded_files == frozenset()


class TestFileClassificationPass:
    """Standalone pass behavior on ChangePassContext."""

    def test_classifies_and_partitions_diff_files(self):
        ctx = ChangePassContext()
        ctx.diff_data = {
            "files": [
                {"file_path": "src/pages/Home.tsx"},
                {"file_path": "server/api.ts"},
                {"file_path": "generated/client.tsx"},
            ]
        }

        ctx = FileClassificationPass().run(ctx)

        assert ctx.file_classifications["src/pages/Home.tsx"].kind == FileKind.FRONTEND
        assert ctx.file_classifications["server/api.ts"].kind == FileKind.BACKEND
        assert ctx.file_classifications["generated/client.tsx"].kind == FileKind.GENERATED

        assert ctx.excluded_files == {"generated/client.tsx"}
        assert ctx.analysis_eligible_files == {"src/pages/Home.tsx", "server/api.ts"}
        assert ctx.metadata["excluded_files"] == ctx.excluded_files

    def test_changed_symbols_pass_skips_excluded_files(self):
        """ChangedSymbolsPass must respect the excluded_files set.

        This test sets up the context directly (without FileClassificationPass)
        to verify ChangedSymbolsPass filtering in isolation.
        """
        excluded = {"src/components/Button.tsx"}

        old_btn = _ts_symbol(
            "ts://src/components/Button.tsx::Button",
            "Button",
            SymbolKind.CLASS,
            "src/components/Button.tsx",
        )
        new_btn = _ts_symbol(
            "ts://src/components/Button.tsx::Button",
            "Button",
            SymbolKind.CLASS,
            "src/components/Button.tsx",
            end_line=77,
        )
        old_api = _ts_symbol(
            "ts://server/api.ts::handler", "handler", SymbolKind.FUNCTION, "server/api.ts"
        )
        new_api = _ts_symbol(
            "ts://server/api.ts::handler",
            "handler",
            SymbolKind.FUNCTION,
            "server/api.ts",
            end_line=12,
        )

        ctx = ChangePassContext()
        ctx.metadata["old_repository_model"] = TestHelper.create_repository_model(
            [old_btn, old_api]
        )
        ctx.metadata["new_repository_model"] = TestHelper.create_repository_model(
            [new_btn, new_api]
        )
        ctx.excluded_files = excluded
        ctx.metadata["excluded_files"] = excluded

        ctx = ChangedSymbolsPass().run(ctx)

        all_output_files = {s.file for s in ctx.added_symbols}
        all_output_files |= {s.file for s in ctx.removed_symbols}
        all_output_files |= {m["symbol"].file for m in ctx.modified_symbols}
        assert all_output_files.isdisjoint(ctx.excluded_files)
        assert any(m["symbol"].file == "server/api.ts" for m in ctx.modified_symbols)
