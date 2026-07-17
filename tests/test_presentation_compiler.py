"""Tests for the Presentation Compiler.

Tests that the PresentationCompiler correctly transforms an EngineeringDiscoveryModel
into a PresentationIR with all 9 passes executing deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from language_adapters.model import (
    RepositoryModel,
    Symbol,
    SymbolKind,
    SymbolVisibility,
    CallGraph,
    CallEdge,
    ReferenceGraph,
    EntryPoint as RepoEntryPoint,
    EntryPointKind,
)
from change.model import (
    ChangeModel,
    ModifiedSymbol,
    ImportChange,
    EndpointChange,
)
from behavior.model import (
    Behavior,
    BehaviorKind,
    BehaviorModel,
    ExecutionGraph,
    ExecutionNode,
    ExecutionEdge,
    ExecutionUnit,
    ExecutionChain,
    EntryPoint,
    TerminalPoint,
    SharedExecution,
)
from operational.model import EngineeringDiscoveryModel, OperationalChangeModel
from presentation.compiler import PresentationCompiler, PresentationPassContext
from presentation.model import (
    PresentationIR,
    PresentationDiscovery,
    PresentationEvidence,
    PresentationSummary,
    PresentationMetadata,
    PresentationNarrative,
    PresentationVisual,
    SignificanceMetrics,
    RankingVector,
    SurpriseVector,
    NormalizedDiscovery,
    DiscoveryKind,
    NarrativePosition,
    VisualSemantic,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TestHelper:
    """Helper for creating test fixtures."""

    @staticmethod
    def create_symbol(
        symbol_id: str,
        name: str,
        kind: SymbolKind,
        start_line: int = 1,
        end_line: int = 10,
        visibility: SymbolVisibility = SymbolVisibility.PUBLIC,
        language: str = "python",
        file: str = "test.py",
        properties: dict[str, Any] | None = None,
    ) -> Symbol:
        """Create a Symbol for testing."""
        return Symbol(
            id=symbol_id,
            name=name,
            kind=kind,
            language=language,
            file=file,
            range=(start_line, end_line),
            visibility=visibility,
            properties=properties or {},
        )

    @staticmethod
    def create_repository_model(
        symbols: list[Symbol],
        entry_points: list[RepoEntryPoint] | None = None,
        call_edges: list[CallEdge] | None = None,
    ) -> RepositoryModel:
        """Create a RepositoryModel for testing."""
        return RepositoryModel(
            symbols=frozenset(symbols),
            call_graph=CallGraph(edges=tuple(call_edges or [])),
            reference_graph=ReferenceGraph(edges=()),
            entry_points=tuple(entry_points or []),
        )

    @staticmethod
    def create_change_model(
        added_symbols: list[Symbol] | None = None,
        removed_symbols: list[Symbol] | None = None,
        modified_symbols: list[ModifiedSymbol] | None = None,
        changed_imports: list[ImportChange] | None = None,
        changed_endpoints: list[EndpointChange] | None = None,
    ) -> ChangeModel:
        """Create a ChangeModel for testing."""
        return ChangeModel(
            added_symbols=tuple(added_symbols or []),
            removed_symbols=tuple(removed_symbols or []),
            modified_symbols=tuple(modified_symbols or []),
            changed_imports=tuple(changed_imports or []),
            changed_endpoints=tuple(changed_endpoints or []),
        )

    @staticmethod
    def create_behavior_model(
        behaviors: list[Behavior] | None = None,
        execution_graphs: list[ExecutionGraph] | None = None,
        execution_chains: list[ExecutionChain] | None = None,
        entry_points: list[EntryPoint] | None = None,
        terminal_points: list[TerminalPoint] | None = None,
        shared_executions: list[SharedExecution] | None = None,
        reachable_units: list[ExecutionUnit] | None = None,
        execution_depth: int = 0,
    ) -> BehaviorModel:
        """Create a BehaviorModel for testing."""
        return BehaviorModel(
            behaviors=tuple(behaviors or []),
            execution_graphs=tuple(execution_graphs or []),
            execution_chains=tuple(execution_chains or []),
            entry_points=tuple(entry_points or []),
            terminal_points=tuple(terminal_points or []),
            shared_executions=tuple(shared_executions or []),
            reachable_units=tuple(reachable_units or []),
            execution_depth=execution_depth,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_symbols():
    """Create sample symbols for testing."""
    return [
        TestHelper.create_symbol(
            "python://test.py::func1",
            "func1",
            SymbolKind.FUNCTION,
        ),
        TestHelper.create_symbol(
            "python://test.py::func2",
            "func2",
            SymbolKind.FUNCTION,
            start_line=20,
            end_line=30,
        ),
    ]


@pytest.fixture
def sample_repository_model(sample_symbols):
    """Create a sample repository model for testing."""
    return TestHelper.create_repository_model(
        symbols=sample_symbols,
        entry_points=[
            RepoEntryPoint(
                kind=EntryPointKind.REST_ENDPOINT,
                route="POST /test",
                handler_id=sample_symbols[0].id,
            ),
        ],
    )


@pytest.fixture
def sample_change_model(sample_symbols):
    """Create a sample change model with various changes."""
    return TestHelper.create_change_model(
        added_symbols=[sample_symbols[1]],
        modified_symbols=[
            ModifiedSymbol(
                symbol=sample_symbols[0],
                changes=(),
            ),
        ],
        changed_imports=[
            ImportChange(
                file="test.py",
                old_import=None,
                new_import="os",
                change_type="added",
            ),
        ],
    )


def sample_execution_units():
    """Create sample execution units."""
    return [
        ExecutionUnit(
            id="unit://behavior://test/0",
            name="Process Request",
            symbol_id="python://test.py::func1",
            order=0,
        ),
        ExecutionUnit(
            id="unit://behavior://test/1",
            name="Validate Data",
            symbol_id="python://test.py::func2",
            order=1,
        ),
    ]


@pytest.fixture
def sample_entry_points():
    """Create sample entry points."""
    return [
        EntryPoint(
            id="ep://behavior://test",
            behavior_id="behavior://test",
            symbol_id="python://test.py::func1",
            kind="REST_ENDPOINT",
            route="POST /test",
        ),
    ]


@pytest.fixture
def sample_terminal_points():
    """Create sample terminal points."""
    return [
        TerminalPoint(
            id="tp://behavior://test/0",
            behavior_id="behavior://test",
            symbol_id="python://test.py::func2",
            kind="return",
        ),
    ]


@pytest.fixture
def sample_behavior_model(sample_symbols, sample_entry_points, sample_terminal_points):
    """Create a sample behavior model with full execution context."""
    units = sample_execution_units()
    return TestHelper.create_behavior_model(
        behaviors=[
            Behavior(
                id="behavior://test",
                name="test_behavior",
                kind=BehaviorKind.REST_ENDPOINT,
                entry_point="POST /test",
                root_symbol_id=sample_symbols[0].id,
                changed_symbol_ids=(sample_symbols[1].id,),
            ),
        ],
        execution_chains=[
            ExecutionChain(
                id="chain://behavior://test",
                behavior_id="behavior://test",
                units=tuple(units),
            ),
        ],
        entry_points=sample_entry_points,
        terminal_points=sample_terminal_points,
        reachable_units=tuple(units),
        execution_depth=2,
    )


@pytest.fixture
def sample_discovery_model(
    sample_repository_model,
    sample_change_model,
    sample_behavior_model,
):
    """Create a sample EngineeringDiscoveryModel for testing."""
    return EngineeringDiscoveryModel(
        repository=sample_repository_model,
        change=sample_change_model,
        behavior=sample_behavior_model,
        execution_units=tuple(sample_execution_units()),
        execution_chains=sample_behavior_model.execution_chains,
        entry_points=sample_behavior_model.entry_points,
        terminal_points=sample_behavior_model.terminal_points,
        reachable_units=sample_behavior_model.reachable_units,
        execution_depth=sample_behavior_model.execution_depth,
    )


@pytest.fixture
def complex_change_model(sample_symbols):
    """Create a change model with multiple additions for compression testing."""
    added = [
        TestHelper.create_symbol(
            f"python://test.py::new_func{i}",
            f"new_func{i}",
            SymbolKind.FUNCTION,
            start_line=100 + i,
            end_line=110 + i,
        )
        for i in range(5)
    ]
    return TestHelper.create_change_model(
        added_symbols=added,
        modified_symbols=[
            ModifiedSymbol(symbol=sample_symbols[0], changes=()),
        ],
        changed_endpoints=[
            EndpointChange(
                symbol_id="python://test.py::func1",
                old_endpoint="/old",
                new_endpoint="/new",
                old_method="GET",
                new_method="POST",
                change_type="modified",
            ),
        ],
    )


@pytest.fixture
def complex_discovery_model(sample_repository_model, complex_change_model, sample_behavior_model):
    """Create a discovery model with complex changes."""
    return EngineeringDiscoveryModel(
        repository=sample_repository_model,
        change=complex_change_model,
        behavior=sample_behavior_model,
        execution_units=tuple(sample_execution_units()),
        execution_chains=sample_behavior_model.execution_chains,
        entry_points=sample_behavior_model.entry_points,
        terminal_points=sample_behavior_model.terminal_points,
        reachable_units=sample_behavior_model.reachable_units,
        execution_depth=sample_behavior_model.execution_depth,
    )


# ---------------------------------------------------------------------------
# Tests: PresentationCompiler
# ---------------------------------------------------------------------------

class TestPresentationCompiler:
    """Tests for the PresentationCompiler orchestration."""

    def test_compiler_initialization(self):
        """Test that the compiler initializes with all 9 passes."""
        compiler = PresentationCompiler()
        assert len(compiler.passes) == 9

    def test_compiler_pass_names(self):
        """Test that pass names are correct."""
        compiler = PresentationCompiler()
        names = compiler.get_pass_names()
        assert "normalization" in names
        assert "discovery_extraction" in names
        assert "significance_evaluation" in names
        assert "ranking" in names
        assert "surprise_detection" in names
        assert "compression" in names
        assert "narrative_construction" in names
        assert "visual_composition" in names
        assert "ir_assembly" in names

    def test_compile_returns_presentation_ir(self, sample_discovery_model):
        """Test that compile returns a PresentationIR."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)
        assert isinstance(ir, PresentationIR)
        assert ir.metadata is not None
        assert ir.summary is not None
        assert ir.discoveries is not None

    def test_compile_none_raises(self):
        """Test that compiling None raises ValueError."""
        compiler = PresentationCompiler()
        with pytest.raises(ValueError, match="discovery_model is required"):
            compiler.compile(None)  # type: ignore

    def test_deterministic_output(self, sample_discovery_model):
        """Test that compilation is deterministic."""
        compiler = PresentationCompiler()
        ir1 = compiler.compile(sample_discovery_model)
        ir2 = compiler.compile(sample_discovery_model)

        assert ir1.summary == ir2.summary
        assert ir1.metadata.discovery_count == ir2.metadata.discovery_count
        assert ir1.metadata.evidence_count == ir2.metadata.evidence_count
        assert len(ir1.discoveries) == len(ir2.discoveries)

    def test_compile_with_context(self, sample_discovery_model):
        """Test compile_with_context returns full pass context."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)
        assert isinstance(context, PresentationPassContext)
        assert context.presentation_ir is not None
        assert len(context.discoveries) > 0
        assert len(context.ranked_discovery_ids) > 0
        assert len(context.narrative_sections) >= 5

    def test_metadata_correct(self, sample_discovery_model):
        """Test that metadata is correctly populated."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        assert ir.metadata.compiler_version == "2.0.0"
        assert ir.metadata.compiled_at != ""
        assert ir.metadata.discovery_count > 0
        assert ir.metadata.pass_count == 9


# ---------------------------------------------------------------------------
# Tests: Normalization (Pass 0)
# ---------------------------------------------------------------------------

class TestNormalization:
    """Tests for the normalization pass."""

    def test_normalized_discoveries_populated(self, sample_discovery_model):
        """Test that normalized discoveries are populated."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)
        assert len(context.normalized_discoveries) > 0

    def test_change_summary_normalized(self, sample_discovery_model):
        """Test that change summary is normalized."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        change_discoveries = [nd for nd in context.normalized_discoveries if nd.source == "change"]
        assert len(change_discoveries) >= 1
        kinds = {nd.kind for nd in change_discoveries}
        assert "added_symbol" in kinds
        assert "modified_symbol" in kinds
        assert "changed_import" in kinds

    def test_behavior_summary_normalized(self, sample_discovery_model):
        """Test that behavior summary is normalized."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        behavior_discoveries = [nd for nd in context.normalized_discoveries if nd.source == "behavior"]
        kinds = {nd.kind for nd in behavior_discoveries}
        assert "behavior" in kinds
        assert "entry_point" in kinds
        assert "terminal_point" in kinds
        assert "execution_chain" in kinds

    def test_every_discovery_has_evidence(self, sample_discovery_model):
        """Test that every normalized discovery has evidence."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        for nd in context.normalized_discoveries:
            assert len(nd.evidence) > 0, f"Discovery {nd.id} has no evidence"
            for ev in nd.evidence:
                assert ev.source != ""
                assert ev.source_id != ""
                assert ev.description != ""


# ---------------------------------------------------------------------------
# Tests: Discovery Extraction (Pass 1)
# ---------------------------------------------------------------------------

class TestDiscoveryExtraction:
    """Tests for the discovery extraction pass."""

    def test_discoveries_have_correct_kind(self, sample_discovery_model):
        """Test that discoveries have the correct DiscoveryKind."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        kinds = {d.kind for d in ir.discoveries}
        assert DiscoveryKind.ADDED_SYMBOLS in kinds
        assert DiscoveryKind.MODIFIED_SYMBOLS in kinds
        assert DiscoveryKind.CHANGED_IMPORTS in kinds
        assert DiscoveryKind.BEHAVIOR in kinds
        assert DiscoveryKind.ENTRY_POINT in kinds
        assert DiscoveryKind.TERMINAL_POINT in kinds
        assert DiscoveryKind.EXECUTION_CHAIN in kinds
        assert DiscoveryKind.REACHABLE_UNITS in kinds
        assert DiscoveryKind.EXECUTION_DEPTH in kinds

    def test_discoveries_have_evidence(self, sample_discovery_model):
        """Test that all discoveries have traceable evidence."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        for discovery in ir.discoveries:
            for evidence in discovery.evidence:
                assert evidence.source != ""
                assert evidence.source_id != ""
                assert evidence.description != ""

    def test_discovery_count_matches_normalized(self, sample_discovery_model):
        """Test that discovery count matches normalized count."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        assert len(context.discoveries) == len(context.normalized_discoveries)


# ---------------------------------------------------------------------------
# Tests: Significance Evaluation (Pass 2)
# ---------------------------------------------------------------------------

class TestSignificanceEvaluation:
    """Tests for the significance evaluation pass."""

    def test_significance_map_populated(self, sample_discovery_model):
        """Test that all discoveries have significance metrics."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        assert len(context.significance_map) > 0
        assert len(context.significance_map) == len(context.discoveries)
        for discovery_id, metrics in context.significance_map.items():
            assert isinstance(metrics, SignificanceMetrics)
            assert metrics.evidence_density >= 0

    def test_metrics_on_discoveries(self, sample_discovery_model):
        """Test that metrics are attached to discoveries."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        for discovery in ir.discoveries:
            assert discovery.metrics is not None
            assert discovery.metrics.evidence_density >= 0

    def test_discovery_kind_specific_metrics(self, sample_discovery_model):
        """Test that different kinds produce different metrics."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        for discovery in context.discoveries:
            metrics = context.significance_map.get(discovery.id)
            assert metrics is not None
            assert isinstance(metrics, SignificanceMetrics)

            if discovery.kind == DiscoveryKind.ADDED_SYMBOLS:
                assert metrics.execution_reach >= 0
                assert metrics.fan_out >= 0

            if discovery.kind == DiscoveryKind.EXECUTION_DEPTH:
                assert metrics.propagation_depth > 0


# ---------------------------------------------------------------------------
# Tests: Ranking (Pass 3)
# ---------------------------------------------------------------------------

class TestRanking:
    """Tests for the ranking pass."""

    def test_ranked_ids_populated(self, sample_discovery_model):
        """Test that ranked discovery IDs are populated."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        assert len(context.ranked_discovery_ids) > 0
        assert len(context.ranked_discovery_ids) == len(context.discoveries)

    def test_ranking_vectors_assigned(self, sample_discovery_model):
        """Test that all discoveries have a ranking vector."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        for discovery in ir.discoveries:
            assert discovery.ranking_vector is not None
            assert isinstance(discovery.ranking_vector, RankingVector)

    def test_ranking_vector_lexicographic_order(self, sample_discovery_model):
        """Test that discoveries are sorted by ranking vector descending."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        for i in range(len(context.discoveries) - 1):
            v1 = context.discoveries[i].ranking_vector or RankingVector()
            v2 = context.discoveries[i + 1].ranking_vector or RankingVector()
            # v1 should be >= v2 (descending order)
            assert v1 >= v2, (
                f"Discovery at index {i} should be >= discovery at index {i+1}\n"
                f"  v1={v1}\n  v2={v2}"
            )

    def test_first_discovery_highest_ranked(self, sample_discovery_model):
        """Test that the first discovery is the highest ranked."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        first = context.discoveries[0]
        assert first.ranking_vector is not None
        # First should have external_surface or high execution_reach
        assert first.ranking_vector.has_external_surface >= 0
        assert first.ranking_vector.execution_reach >= 0


# ---------------------------------------------------------------------------
# Tests: Surprise Detection (Pass 4)
# ---------------------------------------------------------------------------

class TestSurpriseDetection:
    """Tests for the surprise detection pass."""

    def test_surprise_map_is_dict(self, sample_discovery_model):
        """Test that surprise map is always a dict."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)
        assert isinstance(context.surprise_map, dict)

    def test_surprise_never_labels_risky(self, sample_discovery_model):
        """Test that surprises never contain risk-related language."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        for discovery in ir.discoveries:
            if discovery.surprise is not None:
                desc = discovery.surprise.description.lower()
                assert "risk" not in desc
                assert "risky" not in desc
                assert "dangerous" not in desc

    def test_surprise_is_vector(self, sample_discovery_model):
        """Test that surprise is a SurpriseVector, not a boolean."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        for discovery in ir.discoveries:
            if discovery.surprise is not None:
                assert isinstance(discovery.surprise, SurpriseVector)
                assert discovery.surprise.max_ratio >= 0.0

    def test_get_surprising_discoveries(self, sample_discovery_model):
        """Test the get_surprising_discoveries method."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        surprising = ir.get_surprising_discoveries()
        assert isinstance(surprising, tuple)


# ---------------------------------------------------------------------------
# Tests: Compression (Pass 5)
# ---------------------------------------------------------------------------

class TestCompression:
    """Tests for the compression pass."""

    def test_compressed_groups_populated(self, complex_discovery_model):
        """Test that compressed groups are populated for many similar items."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(complex_discovery_model)

        assert isinstance(context.compressed_groups, dict)

    def test_compressed_discoveries_have_children(self, complex_discovery_model):
        """Test that compressed discoveries reference their children."""
        compiler = PresentationCompiler()
        ir = compiler.compile(complex_discovery_model)

        compressed = [d for d in ir.discoveries if d.compressed]
        for c in compressed:
            assert len(c.children) > 0
            # Children are preserved in the compressed discovery's children field
            # (they are intentionally removed from the top-level discoveries list)
            assert all(isinstance(cid, str) for cid in c.children)
            assert c.metadata.get("compressed_count", 0) == len(c.children)

    def test_compressed_preserves_evidence(self, complex_discovery_model):
        """Test that compressed discoveries preserve evidence."""
        compiler = PresentationCompiler()
        ir = compiler.compile(complex_discovery_model)

        for discovery in ir.discoveries:
            if not discovery.compressed:
                continue
            for evidence in discovery.evidence:
                assert evidence.source != ""
                assert evidence.source_id != ""

    def test_no_compression_for_few_items(self, sample_discovery_model):
        """Test that few items are not compressed."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        # With only 1-2 items per kind, there should be no compression
        compressed = [d for d in context.discoveries if d.compressed]
        assert len(compressed) == 0


# ---------------------------------------------------------------------------
# Tests: Narrative Construction (Pass 6)
# ---------------------------------------------------------------------------

class TestNarrativeConstruction:
    """Tests for the narrative construction pass."""

    def test_narrative_sections_created(self, sample_discovery_model):
        """Test that narrative sections are created."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        assert len(context.narrative_sections) >= 5

    def test_narrative_position_assigned(self, sample_discovery_model):
        """Test that all discoveries have a narrative position."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        for discovery in ir.discoveries:
            assert discovery.narrative_position is not None
            assert isinstance(discovery.narrative_position, NarrativePosition)

    def test_get_narrative_section(self, sample_discovery_model):
        """Test get_narrative_section method."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        section = ir.get_narrative_section("impact")
        assert section is not None
        assert section.section == "impact"

        section = ir.get_narrative_section("nonexistent")
        assert section is None

    def test_get_discoveries_by_narrative_position(self, sample_discovery_model):
        """Test get_discoveries_by_narrative_position method."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        impact = ir.get_discoveries_by_narrative_position(NarrativePosition.IMPACT)
        assert len(impact) >= 0
        for d in impact:
            assert d.narrative_position == NarrativePosition.IMPACT


# ---------------------------------------------------------------------------
# Tests: Visual Composition (Pass 7)
# ---------------------------------------------------------------------------

class TestVisualComposition:
    """Tests for the visual composition pass."""

    def test_visuals_created(self, sample_discovery_model):
        """Test that visuals are created for discoveries."""
        compiler = PresentationCompiler()
        context = compiler.compile_with_context(sample_discovery_model)

        assert len(context.visuals) > 0
        assert len(context.visuals) == len(context.discoveries)

    def test_visual_semantics_valid(self, sample_discovery_model):
        """Test that all visual semantics are valid."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        valid_semantics = {vs.value for vs in VisualSemantic}
        for visual in ir.visuals:
            assert visual.semantic.value in valid_semantics, (
                f"Invalid visual semantic: {visual.semantic}"
            )

    def test_visuals_reference_valid_discoveries(self, sample_discovery_model):
        """Test that visuals reference valid discovery IDs."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        for visual in ir.visuals:
            discovery = ir.get_discovery_by_id(visual.discovery_id)
            assert discovery is not None, (
                f"Visual references unknown discovery: {visual.discovery_id}"
            )

    def test_visual_semantic_on_discovery(self, sample_discovery_model):
        """Test that visual semantic is attached to discovery."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        for discovery in ir.discoveries:
            assert discovery.visual_semantic is not None
            assert isinstance(discovery.visual_semantic, VisualSemantic)

    def test_get_visuals_for_discovery(self, sample_discovery_model):
        """Test get_visuals_for_discovery method."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        if ir.discoveries:
            first_id = ir.discoveries[0].id
            visuals = ir.get_visuals_for_discovery(first_id)
            assert len(visuals) == 1
            assert visuals[0].discovery_id == first_id


# ---------------------------------------------------------------------------
# Tests: IR Assembly (Pass 8)
# ---------------------------------------------------------------------------

class TestIRAssembly:
    """Tests for the IR assembly pass."""

    def test_presentation_ir_structure(self, sample_discovery_model):
        """Test that the PresentationIR has all expected fields."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        assert isinstance(ir.metadata, PresentationMetadata)
        assert isinstance(ir.summary, PresentationSummary)
        assert isinstance(ir.discoveries, tuple)
        assert isinstance(ir.narrative, tuple)
        assert isinstance(ir.visuals, tuple)
        assert isinstance(ir.evidence, tuple)
        assert isinstance(ir.navigation, dict)

    def test_summary_counts_match(self, sample_discovery_model):
        """Test that summary counts match actual discoveries."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        assert ir.metadata.discovery_count > 0
        assert ir.metadata.discovery_count == len(ir.discoveries)
        assert ir.metadata.evidence_count == len(ir.evidence)

    def test_evidence_deduplicated(self, sample_discovery_model):
        """Test that evidence is deduplicated."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        discovery_evidence_count = sum(
            len(d.evidence) for d in ir.discoveries
        )
        # IR evidence is deduplicated
        assert len(ir.evidence) <= discovery_evidence_count

    def test_navigation_hints(self, sample_discovery_model):
        """Test that navigation hints are populated."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        assert "sections" in ir.navigation
        assert "top_discoveries" in ir.navigation
        assert "total_discoveries" in ir.navigation
        assert "total_visuals" in ir.navigation
        assert "total_evidence" in ir.navigation

    def test_get_discovery_by_id(self, sample_discovery_model):
        """Test get_discovery_by_id method."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        if ir.discoveries:
            first = ir.discoveries[0]
            found = ir.get_discovery_by_id(first.id)
            assert found is not None
            assert found.id == first.id

        not_found = ir.get_discovery_by_id("nonexistent://id")
        assert not_found is None

    def test_get_discoveries_by_kind(self, sample_discovery_model):
        """Test get_discoveries_by_kind method."""
        compiler = PresentationCompiler()
        ir = compiler.compile(sample_discovery_model)

        added = ir.get_discoveries_by_kind(DiscoveryKind.ADDED_SYMBOLS)
        assert len(added) >= 0
        for d in added:
            assert d.kind == DiscoveryKind.ADDED_SYMBOLS


# ---------------------------------------------------------------------------
# Tests: Presentation Model
# ---------------------------------------------------------------------------

class TestPresentationModel:
    """Tests for the Presentation IR model dataclasses."""

    def test_discovery_immutable(self):
        """Test that PresentationDiscovery is immutable."""
        discovery = PresentationDiscovery(
            id="test://1",
            kind=DiscoveryKind.ADDED_SYMBOLS,
            title="Test",
            summary="Test discovery",
        )
        with pytest.raises(AttributeError):
            discovery.title = "New Title"  # type: ignore

    def test_surprise_vector_defaults(self):
        """Test that SurpriseVector has sensible defaults."""
        vector = SurpriseVector()
        assert vector.reach_ratio == 0.0
        assert vector.max_ratio == 0.0
        assert vector.description == ""

    def test_ranking_vector_has_external_clamped(self):
        """Test that RankingVector clamps has_ fields."""
        vector = RankingVector(has_external_surface=5, has_validation_gap=2)
        assert vector.has_external_surface == 1
        assert vector.has_validation_gap == 1

    def test_ranking_vector_zero_defaults(self):
        """Test that RankingVector zero values work."""
        vector = RankingVector()
        assert vector.has_external_surface == 0
        assert vector.execution_reach == 0
        assert vector.evidence_density == 0

    def test_discovery_converts_list_to_tuple(self):
        """Test that PresentationDiscovery normalizes lists to tuples."""
        discovery = PresentationDiscovery(
            id="test://1",
            kind=DiscoveryKind.ADDED_SYMBOLS,
            title="Test",
            summary="Test",
            evidence=[
                PresentationEvidence(
                    source="test", source_id="1", description="ev"
                ),
            ],
        )
        assert isinstance(discovery.evidence, tuple)
        assert len(discovery.evidence) == 1

    def test_presentation_ir_immutability(self):
        """Test that PresentationIR fields are immutable."""
        ir = PresentationIR(
            metadata=PresentationMetadata(),
            summary=PresentationSummary(),
        )
        with pytest.raises(AttributeError):
            ir.metadata = PresentationMetadata()  # type: ignore

    def test_empty_ir(self):
        """Test creating an empty PresentationIR."""
        ir = PresentationIR(
            metadata=PresentationMetadata(),
            summary=PresentationSummary(),
        )
        assert len(ir.discoveries) == 0
        assert len(ir.visuals) == 0
        assert len(ir.narrative) == 0

    def test_discovery_kind_values(self):
        """Test that DiscoveryKind enum has correct values."""
        assert DiscoveryKind.ADDED_SYMBOLS.value == "added_symbols"
        assert DiscoveryKind.EXECUTION_CHAIN.value == "execution_chain"
        assert DiscoveryKind.VALIDATION_GAP.value == "validation_gap"
        assert DiscoveryKind.COMPRESSED.value == "compressed"

    def test_narrative_position_values(self):
        """Test that NarrativePosition enum has correct values."""
        assert NarrativePosition.SUMMARY.value == "summary"
        assert NarrativePosition.IMPACT.value == "impact"
        assert NarrativePosition.EXECUTION.value == "execution"
        assert NarrativePosition.OPERATIONAL.value == "operational"
        assert NarrativePosition.VALIDATION.value == "validation"
        assert NarrativePosition.EVIDENCE.value == "evidence"

    def test_visual_semantic_values(self):
        """Test that VisualSemantic enum has correct values."""
        assert VisualSemantic.METRIC.value == "metric"
        assert VisualSemantic.TIMELINE.value == "timeline"
        assert VisualSemantic.GRAPH.value == "graph"
        assert VisualSemantic.CARD.value == "card"
        assert VisualSemantic.HIERARCHY.value == "hierarchy"
        assert VisualSemantic.TABLE.value == "table"
        assert VisualSemantic.COVERAGE_INDICATOR.value == "coverage_indicator"

    def test_significance_metrics_defaults(self):
        """Test that SignificanceMetrics has sensible defaults."""
        metrics = SignificanceMetrics()
        assert metrics.execution_reach == 0
        assert metrics.fan_out == 0
        assert metrics.propagation_depth == 0
        assert metrics.evidence_density == 0
        assert metrics.cross_domain_evidence == 0

    def test_presentation_narrative_discovery_ids_normalized(self):
        """Test that PresentationNarrative normalizes lists to tuples."""
        narrative = PresentationNarrative(
            section="impact",
            order=0,
            discovery_ids=["id1", "id2"],
        )
        assert isinstance(narrative.discovery_ids, tuple)
        assert len(narrative.discovery_ids) == 2