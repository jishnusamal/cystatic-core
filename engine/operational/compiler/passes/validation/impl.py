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

from engine.operational.compiler.passes.base import (
    OperationalCompilerPass,
    OperationalPassContext,
)
from engine.repository.model import RepositoryModel, Symbol, SymbolKind


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
        for attr in (
            "unit_tests",
            "integration_tests",
            "e2e_tests",
            "benchmarks",
            "production_replays",
            "coverage_links",
        ):
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
    "integration",
    "integrate",
    "e2e",
    "functional",
}

_E2E_PATTERNS = {
    "e2e",
    "end_to_end",
    "endtoend",
    "smoke",
    "acceptance",
}

_BENCHMARK_PATTERNS = {
    "benchmark",
    "bench",
    "perf_test",
    "performance",
}

_REPLAY_PATTERNS = {
    "replay",
    "record_replay",
    "production_replay",
}

_COVERAGE_PATTERNS = {
    "coverage",
    "coveragerc",
    "codecov",
    "coveralls",
    "lcov",
    "nyc_output",
    "jacoco",
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

        # Use cached values from context
        affected_symbol_ids = context.get_affected_symbol_ids()
        symbol_map = context.get_symbol_map()

        # Build index/lookup tables for references and call graph
        from collections import defaultdict

        ref_by_target: dict[str, set[str]] = defaultdict(set)
        if (
            hasattr(repo, "reference_graph")
            and repo.reference_graph
            and repo.reference_graph.edges
        ):
            for edge in repo.reference_graph.edges:
                ref_by_target[edge.target_id].add(edge.source_id)
        elif hasattr(repo, "get_references_to"):
            for affected_id in affected_symbol_ids:
                for ref in repo.get_references_to(affected_id):
                    ref_by_target[ref.target_id].add(ref.source_id)

        callees_of = context.get_callees_of()
        callers_of = context.get_callers_of()

        # Pre-compute all symbol IDs that reference or call/are called by any affected symbol
        references_affected_set: set[str] = set()
        for affected_id in affected_symbol_ids:
            references_affected_set.update(ref_by_target.get(affected_id, ()))
            references_affected_set.update(callers_of.get(affected_id, ()))
            references_affected_set.update(callees_of.get(affected_id, ()))

        # Helper to safely get file path from Symbol fact or legacy Symbol model
        def get_symbol_file_path(s: Symbol) -> str:
            if hasattr(s, "file") and s.file:
                return s.file
            if hasattr(s, "file_id") and s.file_id is not None:
                if hasattr(repo, "get_file"):
                    f = repo.get_file(s.file_id)
                    if f is not None:
                        return str(f.path)
                if isinstance(s.file_id, str):
                    return s.file_id
            return ""

        # Get affected files
        affected_files: set[str] = set()
        for sid in affected_symbol_ids:
            if sid in symbol_map:
                f_path = get_symbol_file_path(symbol_map[sid])
                if f_path:
                    affected_files.add(f_path)

        # Classify test symbols
        unit_tests: list[Symbol] = []
        integration_tests: list[Symbol] = []
        e2e_tests: list[Symbol] = []
        benchmarks: list[Symbol] = []
        production_replays: list[str] = []
        coverage_links: list[str] = []

        # Strategy 1: If repo implements get_tests() (RepositoryQuery / RepositoryView),
        # use it directly per affected symbol. This is the primary path for the new architecture.
        if hasattr(repo, "get_tests"):
            seen_test_sym_ids: set = set()
            for affected_id in affected_symbol_ids:
                for test_rel in repo.get_tests(affected_id):
                    test_sym_id = test_rel.test_symbol_id
                    if test_sym_id in seen_test_sym_ids:
                        continue
                    seen_test_sym_ids.add(test_sym_id)

                    # Resolve the test symbol for classification
                    test_sym = None
                    if hasattr(repo, "get_symbol"):
                        test_sym = repo.get_symbol(test_sym_id)
                    if test_sym is None:
                        test_sym = symbol_map.get(str(test_sym_id)) or symbol_map.get(
                            test_sym_id
                        )
                    if test_sym is None:
                        continue

                    rel_type_str = (
                        test_rel.relationship_type.value
                        if hasattr(test_rel.relationship_type, "value")
                        else str(test_rel.relationship_type)
                    )
                    if rel_type_str == "e2e":
                        e2e_tests.append(test_sym)
                    elif rel_type_str == "integration":
                        integration_tests.append(test_sym)
                    else:
                        # Fall back to name/file classification for unit/benchmark
                        f_path = get_symbol_file_path(test_sym)
                        test_category = self._classify_test(test_sym, f_path)
                        if test_category == "benchmark":
                            benchmarks.append(test_sym)
                        elif test_category == "e2e":
                            e2e_tests.append(test_sym)
                        elif test_category == "integration":
                            integration_tests.append(test_sym)
                        else:
                            unit_tests.append(test_sym)

        # Strategy 2: Fallback — scan all available symbols.
        # Used when: no get_tests() method (legacy RepositoryModel) OR no test rels were found.
        if (
            not unit_tests
            and not integration_tests
            and not e2e_tests
            and not benchmarks
        ):
            symbols_to_scan = (
                repo.symbols if hasattr(repo, "symbols") else symbol_map.values()
            )
            for sym in symbols_to_scan:
                # 1. Test classification
                if sym.kind == SymbolKind.FUNCTION or sym.kind == SymbolKind.METHOD:
                    f_path = get_symbol_file_path(sym)
                    test_category = self._classify_test(sym, f_path)
                    if test_category is not None:
                        sym_id_str = str(sym.id)
                        if (
                            sym_id_str in references_affected_set
                            or sym.id in references_affected_set
                        ):
                            if test_category == "unit":
                                unit_tests.append(sym)
                            elif test_category == "integration":
                                integration_tests.append(sym)
                            elif test_category == "e2e":
                                e2e_tests.append(sym)
                            elif test_category == "benchmark":
                                benchmarks.append(sym)

                # 2. Production replay detection
                replay_ref = self._detect_replay(sym)
                if replay_ref:
                    production_replays.append(replay_ref)

                # 3. Coverage detection
                f_path = get_symbol_file_path(sym)
                cov_ref = self._detect_coverage(sym, f_path)
                if cov_ref:
                    coverage_links.append(cov_ref)

        # Add affected files that are coverage configs
        for file_path in affected_files:
            if any(p in file_path.lower() for p in _COVERAGE_PATTERNS):
                coverage_links.append(file_path)

        validation_model = ValidationModel(
            unit_tests=tuple(sorted(unit_tests, key=lambda s: str(s.id))),
            integration_tests=tuple(sorted(integration_tests, key=lambda s: str(s.id))),
            e2e_tests=tuple(sorted(e2e_tests, key=lambda s: str(s.id))),
            benchmarks=tuple(sorted(benchmarks, key=lambda s: str(s.id))),
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
            api=model.api if hasattr(model, "api") else None,
            metrics=model.metrics if hasattr(model, "metrics") else None,
        )

        return context

    @staticmethod
    def _classify_test(sym: Symbol, file_path: str = "") -> str | None:
        """Classify a symbol into a test category."""
        name_lower = sym.name.lower()
        file_lower = file_path.lower() if file_path else (sym.file.lower() if hasattr(sym, "file") else "")

        # Check benchmark patterns first
        if any(p in name_lower for p in _BENCHMARK_PATTERNS):
            return "benchmark"
        if file_lower and any(p in file_lower for p in _BENCHMARK_PATTERNS):
            return "benchmark"

        # Check E2E patterns
        if file_lower and any(p in file_lower for p in _E2E_PATTERNS):
            return "e2e"
        if any(p in name_lower for p in _E2E_PATTERNS):
            return "e2e"

        # Check integration patterns
        if file_lower and any(p in file_lower for p in _INTEGRATION_PATTERNS):
            return "integration"
        if any(p in name_lower for p in _INTEGRATION_PATTERNS):
            return "integration"

        # Check test file patterns for unit tests
        for pattern in _TEST_FILE_PATTERNS:
            if (file_lower and pattern in file_lower) or pattern in name_lower:
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

        Deprecated: Use index-based lookup in references_affected_set instead.
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
        props = getattr(sym, "properties", {})
        if props.get("replay") or props.get("record_replay"):
            return str(props.get("replay", props.get("record_replay")))
        return None

    @staticmethod
    def _detect_coverage(sym: Symbol, file_path: str = "") -> str | None:
        """Detect coverage references."""
        name_lower = sym.name.lower()
        if any(p in name_lower for p in _COVERAGE_PATTERNS):
            return sym.name
        file_lower = file_path.lower() if file_path else (sym.file.lower() if hasattr(sym, "file") else "")
        if file_lower and any(p in file_lower for p in _COVERAGE_PATTERNS):
            return file_lower
        props = getattr(sym, "properties", {})
        if props.get("coverage") or props.get("coverage_file"):
            return str(props.get("coverage", props.get("coverage_file")))
        return None
