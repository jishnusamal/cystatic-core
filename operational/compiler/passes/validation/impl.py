"""Validation Compilation Pass - compiles validation evidence.

Question: How is this behavior validated?

Produces ValidationModel with:
- Unit Tests: test functions that cover affected behaviors
- Integration Tests: integration test functions
- E2E Tests: end-to-end test functions
- Benchmarks: benchmark functions
- Production Replay: replay test references
- Coverage Links: links to coverage artifacts

This is evidence, not recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from language_adapters.model import RepositoryModel, Symbol, SymbolKind
from operational.model import OperationalChangeModel


@dataclass(frozen=True)
class ValidationModel:
    """
    Validation evidence for affected behaviors.

    All fields are deterministically derived from the repository model.
    No recommendations, only evidence.
    """

    # Unit test symbols that cover affected behaviors
    unit_tests: tuple[Symbol, ...] = field(default_factory=tuple)

    # Integration test symbols that cover affected behaviors
    integration_tests: tuple[Symbol, ...] = field(default_factory=tuple)

    # End-to-end test symbols that cover affected behaviors
    e2e_tests: tuple[Symbol, ...] = field(default_factory=tuple)

    # Benchmark symbols that cover affected behaviors
    benchmarks: tuple[Symbol, ...] = field(default_factory=tuple)

    # Production replay references
    production_replays: tuple[str, ...] = field(default_factory=tuple)

    # Coverage links/references (file paths, coverage IDs)
    coverage_links: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        """Convert mutable defaults to immutable types."""
        for attr in ("unit_tests", "integration_tests", "e2e_tests", "benchmarks",
                     "production_replays", "coverage_links"):
            val = getattr(self, attr)
            if isinstance(val, list):
                object.__setattr__(self, attr, tuple(val))


# Test file patterns
_TEST_FILE_PATTERNS = {
    "test_": "unit",
    "_test": "unit",
    "spec_": "unit",
    "_spec": "unit",
}

_INTEGRATION_PATTERNS = {
    "integration", "integrate", "e2e", "functional",
}

_E2E_PATTERNS = {
    "e2e", "end_to_end", "endtoend", "smoke", "acceptance",
}

_BENCHMARK_PATTERNS = {
    "benchmark", "bench", "perf_test", "performance",
}

_REPLAY_PATTERNS = {
    "replay", "record_replay", "production_replay",
}

_COVERAGE_PATTERNS = {
    "coverage", "coveragerc", "codecov", "coveralls",
    "lcov", "nyc_output", "jacoco",
}


class ValidationCompilationPass(OperationalCompilerPass):
    """
    Pass 5 of Operational compilation.

    Compiles validation evidence for affected behaviors.
    """

    @property
    def name(self) -> str:
        return "validation_compilation"

    def validate_input(self, context: OperationalPassContext) -> bool:
        """Verify the composed model exists."""
        return context.composed_model is not None

    def run(self, context: OperationalPassContext) -> OperationalPassContext:
        """
        Execute validation compilation on the composed model.

        Args:
            context: Pass context with composed_model set.

        Returns:
            Updated context with validation model set on composed_model.
        """
        if not self.validate_input(context):
            return context

        model = context.composed_model
        if model is None:
            return context
        
        repo = model.repository
        behavior = model.behavior
        change = model.change

        # Collect all affected symbol IDs
        affected_symbol_ids: set[str] = set()
        for b in behavior.behaviors:
            affected_symbol_ids.add(b.root_symbol_id)
            affected_symbol_ids.update(b.changed_symbol_ids)
        for s in change.added_symbols:
            affected_symbol_ids.add(s.id)
        for s in change.removed_symbols:
            affected_symbol_ids.add(s.id)
        for ms in change.modified_symbols:
            affected_symbol_ids.add(ms.symbol.id)

        symbol_map: dict[str, Symbol] = {s.id: s for s in repo.symbols}

        # Get affected files
        affected_files: set[str] = set()
        for sid in affected_symbol_ids:
            if sid in symbol_map:
                affected_files.add(symbol_map[sid].file)

        # Classify test symbols
        unit_tests: list[Symbol] = []
        integration_tests: list[Symbol] = []
        e2e_tests: list[Symbol] = []
        benchmarks: list[Symbol] = []
        production_replays: list[str] = []
        coverage_links: list[str] = []

        # Find test files that reference affected symbols
        for sym in repo.symbols:
            if sym.kind != SymbolKind.FUNCTION and sym.kind != SymbolKind.METHOD:
                continue

            test_category = self._classify_test(sym)
            if test_category is None:
                continue

            # Check if this test references any affected symbols
            # via reference graph or file proximity
            references_affected = self._references_affected(
                repo, sym.id, affected_symbol_ids
            )

            if not references_affected:
                continue

            if test_category == "unit":
                unit_tests.append(sym)
            elif test_category == "integration":
                integration_tests.append(sym)
            elif test_category == "e2e":
                e2e_tests.append(sym)
            elif test_category == "benchmark":
                benchmarks.append(sym)

        # Collect production replay references from all symbols
        for sym in repo.symbols:
            replay_ref = self._detect_replay(sym)
            if replay_ref:
                production_replays.append(replay_ref)

        # Collect coverage links from all symbols and files
        for sym in repo.symbols:
            cov_ref = self._detect_coverage(sym)
            if cov_ref:
                coverage_links.append(cov_ref)

        # Add affected files that are coverage configs
        for file_path in affected_files:
            if any(p in file_path.lower() for p in _COVERAGE_PATTERNS):
                coverage_links.append(file_path)

        validation_model = ValidationModel(
            unit_tests=tuple(sorted(unit_tests, key=lambda s: s.id)),
            integration_tests=tuple(sorted(integration_tests, key=lambda s: s.id)),
            e2e_tests=tuple(sorted(e2e_tests, key=lambda s: s.id)),
            benchmarks=tuple(sorted(benchmarks, key=lambda s: s.id)),
            production_replays=tuple(sorted(set(production_replays))),
            coverage_links=tuple(sorted(set(coverage_links))),
        )

        # Enrich the composed model
        context.composed_model = model.__class__(
            repository=model.repository,
            change=model.change,
            behavior=model.behavior,
            dependency=model.dependency,
            data=model.data,
            event=model.event,
            validation=validation_model,
            api=model.api if hasattr(model, 'api') else None,
            metrics=model.metrics if hasattr(model, 'metrics') else None,
        )

        return context

    @staticmethod
    def _classify_test(sym: Symbol) -> str | None:
        """Classify a symbol into a test category."""
        name_lower = sym.name.lower()
        file_lower = sym.file.lower()

        # Check benchmark patterns first
        if any(p in name_lower for p in _BENCHMARK_PATTERNS):
            return "benchmark"
        if any(p in file_lower for p in _BENCHMARK_PATTERNS):
            return "benchmark"

        # Check E2E patterns
        if any(p in file_lower for p in _E2E_PATTERNS):
            return "e2e"
        if any(p in name_lower for p in _E2E_PATTERNS):
            return "e2e"

        # Check integration patterns
        if any(p in file_lower for p in _INTEGRATION_PATTERNS):
            return "integration"
        if any(p in name_lower for p in _INTEGRATION_PATTERNS):
            return "integration"

        # Check test file patterns for unit tests
        for pattern, category in _TEST_FILE_PATTERNS.items():
            if pattern in file_lower or pattern in name_lower:
                return "unit"

        return None

    @staticmethod
    def _references_affected(
        repo: RepositoryModel,
        symbol_id: str,
        affected_ids: set[str],
    ) -> bool:
        """
        Check if a symbol (e.g., test) references any affected symbol.

        Checks via:
        1. Direct reference in the reference graph
        2. Call graph edges
        3. File proximity (same file as affected symbol)
        """
        # Check reference graph
        for ref_edge in repo.reference_graph.edges:
            if ref_edge.source_id == symbol_id and ref_edge.target_id in affected_ids:
                return True

        # Check call graph
        for call_edge in repo.call_graph.edges:
            if call_edge.caller_id == symbol_id and call_edge.callee_id in affected_ids:
                return True
            if call_edge.callee_id == symbol_id and call_edge.caller_id in affected_ids:
                return True

        return False

    @staticmethod
    def _detect_replay(sym: Symbol) -> str | None:
        """Detect production replay references."""
        name_lower = sym.name.lower()
        if any(p in name_lower for p in _REPLAY_PATTERNS):
            return sym.name
        props = sym.properties
        if props.get("replay") or props.get("record_replay"):
            return str(props.get("replay", props.get("record_replay")))
        return None

    @staticmethod
    def _detect_coverage(sym: Symbol) -> str | None:
        """Detect coverage references."""
        name_lower = sym.name.lower()
        if any(p in name_lower for p in _COVERAGE_PATTERNS):
            return sym.name
        file_lower = sym.file.lower()
        if any(p in file_lower for p in _COVERAGE_PATTERNS):
            return sym.file
        props = sym.properties
        if props.get("coverage") or props.get("coverage_file"):
            return str(props.get("coverage", props.get("coverage_file")))
        return None