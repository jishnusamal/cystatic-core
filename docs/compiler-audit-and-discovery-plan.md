# Compiler Audit & Discovery Compiler Implementation Plan

## 1. Audit of Existing Reusable Compiler Passes

### Stage 1: Repository Compiler (`language_adapters/base/compiler.py` - `_ModelCompiler`)

| Pass | What It Produces | Reusable For |
|------|-----------------|--------------|
| **Pass 1: Symbol Collection** | Symbols (functions, classes, methods, imports) | All downstream passes need symbol maps |
| **Pass 2: Reference Resolution** | `ReferenceGraph` (import → symbol edges) | Fan-in, fan-out, dependency traversal |
| **Pass 3: Call Graph** | `CallGraph` (caller → callee edges) | Reachability, execution chains, propagation, fan-in/out |
| **Pass 4: Endpoint Discovery** | `EntryPoint` list (REST routes, handler_ids) | API surface, boundary detection, entry points |
| **Pass 5: Type Relationships** | `TypeRelationshipGraph` (inheritance, composition) | System coupling, boundary detection |
| **Pass 6: Async Entry Points** | `AsyncEntryPoint` list (workers, queues, cron) | Event propagation, async chains |
| **Pass 7: Persistence Models** | `PersistenceModel` list (ORM models, tables) | Data propagation, data surface |
| **Pass 8: Repository Methods** | `RepositoryMethod` list (data access) | Data propagation |
| **Pass 9: Event Constructs** | `EventConstruct` list (publish/subscribe) | Event propagation |
| **Pass 10: Test Definitions** | `TestDefinition` list | Validation coverage, validation gaps |
| **Pass 11: Configuration References** | `ConfigurationReference` list (env vars, config) | Operational config scope |

### Stage 2: Change Compiler (`change/compiler/`)

| Pass | What It Produces | Reusable For |
|------|-----------------|--------------|
| **ChangedSymbolsPass** | Added/removed/modified symbol sets | Every discovery pass needs changed symbols |
| **ChangeClassificationPass** | Change types per symbol (body, signature, decorator, etc.) | Significance, surprise, risk indicators |

### Stage 3: Behavior Compiler (`behavior/compiler/`)

| Pass | What It Produces | Reusable For |
|------|-----------------|--------------|
| **BehaviorDiscoveryPass (1)** | `Behavior` list (BFS upward to entry points) | Reachability, execution chains, entry points |
| **BehaviorGraphPass (2)** | `ExecutionGraph` per behavior (BFS downward from root) | Execution chains, propagation depth |
| **ExecutionChainPass (3)** | `ExecutionChain` per behavior (ordered units) | Execution surface, path analysis |
| **EntryPointPass (4)** | `EntryPoint` per behavior | Boundary detection, API surface |
| **TerminalPointPass (5)** | `TerminalPoint` per behavior (leaf nodes) | Boundary detection, terminal analysis |
| **SharedExecutionPass (6)** | `SharedExecution` (symbols used by >1 behavior) | Fan-in, coupling detection, shared infrastructure |
| **ReachableUnitsPass (7)** | `ExecutionUnit` reachable from changed symbols | Blast radius, impact scope |

### Stage 4: Operational Compiler (`operational/compiler/`)

| Pass | What It Produces | Reusable For |
|------|-----------------|--------------|
| **ModelCompositionPass** | Unified `OperationalChangeModel` | Foundation for all enrichment |
| **ConsistencyValidationPass** | Validation errors (orphaned refs, missing imports) | Structural integrity |
| **DependencyCompilationPass (3)** | `DependencyModel`: callers, dependents, fan_in, fan_out, cross_service_references, dependency_depth | **Fan-in, fan-out, cross-service refs, dependency depth, service boundary detection** |
| **DataCompilationPass (4)** | `DataModel`: models, tables, reads, writes, transactions, caches, external_storage | **Data propagation, storage surface** |
| **EventCompilationPass (5)** | `EventModel`: published_events, consumed_events, queues, workers, async_chains, event_graph | **Event propagation, async chains, event coupling** |
| **APICompilationPass (6)** | `APIModel`: rest, graphql, rpc, cli, cron, workers | **API surface, external boundary detection** |
| **ValidationCompilationPass (7)** | `ValidationModel`: unit_tests, integration_tests, e2e_tests | **Validation coverage, validation gaps** |
| **MetricsCompilationPass (8)** | `DiscoveryMetrics`: aggregate counts | Summary metrics, blast radius |

### Stage 5: Engineering Discovery Compiler (`operational/compiler/engineering_discovery_compiler.py`)

This is currently a **projection-only** pass. It copies fields from `OperationalChangeModel` into `EngineeringDiscoveryModel`. No analysis.

### Stage 6: Presentation Compiler (`presentation/compiler/`)

| Pass | What It Produces | Should Move To |
|------|-----------------|----------------|
| **NormalizationPass (0)** | `NormalizedDiscovery` list from EDM | Stays in Presentation (format conversion) |
| **DiscoveryExtractionPass (1)** | `PresentationDiscovery` objects | Stays in Presentation |
| **SignificanceEvaluationPass (2)** | `SignificanceMetrics` per discovery (reach, fan_out, boundary, depth, etc.) | **Should move to Discovery Compiler** |
| **RankingPass (3)** | `RankingVector` (lexicographic ORDER BY) | **Should move to Discovery Compiler** |
| **SurpriseDetectionPass (4)** | `SurpriseVector` (ratios: change_size vs impact) | **Should move to Discovery Compiler** |
| **CompressionPass (5)** | Compressed discovery groups | **Should move to Discovery Compiler** (lossless grouping) |
| **NarrativeConstructionPass (6)** | Narrative sections (Impact → Execution → Operational → Validation) | Stays in Presentation (ordering for humans) |
| **VisualCompositionPass (7)** | Visual semantics (metric, timeline, graph, card, etc.) | Stays in Presentation (semantic-to-platform mapping) |
| **IRAssemblyPass (8)** | `PresentationIR` | Stays in Presentation |

---

## 2. Mapping: Existing Compiler Outputs → Desired Discovery Passes

| Desired Discovery | Existing Implementation | Existing Path | Reuse Strategy |
|------------------|----------------------|---------------|----------------|
| **Reachability** | ✅ Exists | `behavior/compiler/passes/reachable_units/` + `operational/compiler/passes/dependency/` | Reuse `BehaviorModel.reachable_units` and `DependencyModel.dependency_depth` |
| **Execution Chains** | ✅ Exists | `behavior/compiler/passes/execution_chain/` | Reuse `BehaviorModel.execution_chains` |
| **Shared Execution** | ✅ Exists | `behavior/compiler/passes/shared_execution/` | Reuse `BehaviorModel.shared_executions` |
| **Fan-in** | ✅ Exists | `operational/compiler/passes/dependency/impl.py` `DependencyModel.fan_in` | Reuse directly |
| **Fan-out** | ✅ Exists | `operational/compiler/passes/dependency/impl.py` `DependencyModel.fan_out` | Reuse directly |
| **Dependency Traversal** | ✅ Exists | `operational/compiler/passes/dependency/impl.py` `DependencyModel.{callers, dependents}` | Reuse directly |
| **Cross-Service References** | ✅ Exists | `operational/compiler/passes/dependency/impl.py` `DependencyModel.cross_service_references` | Reuse directly |
| **Execution Depth** | ✅ Exists | `behavior/compiler/compiler.py` `BehaviorModel.execution_depth` + `DependencyModel.dependency_depth` | Reuse directly |
| **Propagation** | ✅ Exists | `operational/compiler/passes/dependency/` BFS outward + `behavior/compiler/passes/behavior_graph/` BFS downward | Reuse adjacency from call graph |
| **Validation Gaps** | ✅ Exists | `operational/compiler/passes/validation/` `ValidationModel` | Matched vs unmatched tests |
| **Boundary Detection** | ✅ Exists | `operational/compiler/passes/dependency/` `_service_of()` extraction + cross_service_references | Reuse directly |
| **API Surface** | ✅ Exists | `operational/compiler/passes/api/` `APIModel` | Reuse directly |
| **Event Propagation** | ✅ Exists | `operational/compiler/passes/events/` `EventModel.{async_chains, event_graph}` | Reuse directly |
| **Data Propagation** | ✅ Exists | `operational/compiler/passes/data/` `DataModel` | Reuse directly |
| **Ranking** | ⚠️ Partially exists | `presentation/compiler/passes/ranking.py` `RankingVector` (lexicographic ORDER BY) | Move to Discovery Compiler |
| **Surprise Detection** | ⚠️ Partially exists | `presentation/compiler/passes/surprise_detection.py` (ratio-based) | Move to Discovery Compiler |
| **Significance Evaluation** | ⚠️ Partially exists | `presentation/compiler/passes/significance_evaluation.py` | Move to Discovery Compiler |
| **Compression** | ⚠️ Partially exists | `presentation/compiler/passes/compression.py` (grouping only) | Move to Discovery Compiler |

---

## 3. Missing Discovery Passes

Some desired discoveries require **new** passes on the existing models:

| Missing Discovery | Why | Input Models Needed | Approach |
|------------------|-----|-------------------|----------|
| **Hidden Relationship Detection** | Not currently computed | `ReferenceGraph`, `TypeRelationshipGraph`, `EventModel.event_graph` | Graph intersection: find symbols connected via multiple relationship types (call + type + event) that aren't obvious |
| **Largest Execution Surface** | Per-symbol reachability count not aggregated | `BehaviorModel.execution_chains`, `BehaviorModel.reachable_units` | For each changed symbol, count total execution units reachable across all behaviors; rank by count |
| **Architectural Boundary Crossings** | Cross-service edges counted but not ranked by "surprise" | `DependencyModel.cross_service_references`, symbol file->module mapping | Compare service boundary against expected modular boundaries; flag unexpected crossings |
| **Unexpected Service Coupling** | Coupling exists in call graph but no "unexpectedness" metric | `DependencyModel`, `TypeRelationshipGraph`, import structure | Compute distance between symbol locations vs. reference locations; flag calls across distant modules |
| **Dominant Execution Paths** | All paths equal, no "dominance" ranking | `ExecutionChain`, execution graph node frequency across behaviors | Frequency analysis: count how many behaviors traverse each symbol; rank by cross-behavior usage |
| **Boundary Invariance** | No "unchanged boundary" detection | Both base and head `RepositoryModel.entry_points` | Diff entry points between base and head; report ones that had changed reachable symbols but unchanged interface |
| **Significance Ranking** | Requires combining multiple metrics into a rankable vector | All existing metrics | Lexicographic ORDER BY (already exists in presentation layer; needs to produce Discovery objects) |
| **Minimum Surprising Discovery** | Reverse of surprise: which changed symbol has least impact relative to expectation | `ChangeModel`, `BehaviorModel` | Compute impact/change ratio; find lowest ratios |
| **Validation Gap Ranking** | Gaps listed but not ranked by risk/importance | `ValidationModel`, `DependencyModel.fan_out` | Weight validation gaps by fan-out: gaps on high-fan-out symbols ranked higher |

---

## 4. Proposed Discovery IR

### Discovery Objects

```python
@dataclass(frozen=True)
class Discovery:
    """A single engineering discovery emitted by the Discovery Compiler.
    
    The statement must already express the discovery in natural language.
    Evidence supports discoveries — evidence is NOT the discovery.
    """
    id: str                              # Stable identifier
    kind: DiscoveryKind                  # Semantic kind
    statement: str                       # "CustomerWithMembers is reachable from five REST endpoints."
    importance: float                    # 0.0 to 1.0 (from ranking vector normalization)
    support: DiscoverySupport            # Deterministic backing data
    evidence: tuple[DiscoveryEvidence, ...]  # Traceable evidence
    metadata: dict[str, Any]             # Additional structured data


@dataclass(frozen=True)
class DiscoverySupport:
    """Deterministic backing for a discovery.
    
    Contains the raw measurements that justify the discovery statement.
    Every field is directly traceable to compiler evidence.
    """
    # Core measurements
    execution_reach: int = 0
    fan_in: int = 0
    fan_out: int = 0
    propagation_depth: int = 0
    boundary_crossings: int = 0
    
    # Surface areas
    external_surface: int = 0
    data_surface: int = 0
    event_surface: int = 0
    validation_coverage: int = 0
    validation_gaps: int = 0
    
    # Coupling
    shared_by_count: int = 0
    cross_service_count: int = 0
    cross_module_count: int = 0
    
    # Change context
    changed_symbol_count: int = 0
    changed_file_count: int = 0
    
    # Ranking vector (lexicographic ORDER BY components)
    ranking_vector: tuple[int, ...] = field(default_factory=tuple)
    
    # Surprise vector (ratios)
    surprise_ratios: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveryEvidence:
    """A single piece of evidence backing a discovery.
    
    Always traceable to a compiler artifact location.
    """
    source: str                          # compiler stage: "behavior", "operational", "change"
    source_id: str                       # stable identifier in that stage
    description: str                     # human-readable description
    evidence_ref: str                    # URI to the underlying artifact


class DiscoveryKind(str, Enum):
    """Classification of discovery type."""
    REACHABILITY = "reachability"
    EXECUTION_CHAIN = "execution_chain"
    SHARED_EXECUTION = "shared_execution"
    FAN_IN = "fan_in"
    FAN_OUT = "fan_out"
    DEPENDENCY = "dependency"
    CROSS_SERVICE = "cross_service"
    EXECUTION_DEPTH = "execution_depth"
    PROPAGATION = "propagation"
    VALIDATION_GAP = "validation_gap"
    BOUNDARY_CROSSING = "boundary_crossing"
    API_SURFACE = "api_surface"
    EVENT_PROPAGATION = "event_propagation"
    DATA_PROPAGATION = "data_propagation"
    SURPRISE = "surprise"
    HIDDEN_RELATIONSHIP = "hidden_relationship"
    DOMINANT_PATH = "dominant_path"
    COUPLING = "unexpected_coupling"
    BOUNDARY_INVARIANCE = "boundary_invariance"
```

### DiscoveryIR (output of Discovery Compiler)

```python
@dataclass(frozen=True)
class DiscoveryIR:
    """The canonical discovery intermediate representation.
    
    Contains all deterministic discoveries about a code change.
    The Presentation Compiler consumes this IR and produces 
    platform-specific output without performing any analysis.
    """
    metadata: DiscoveryMetadata
    discoveries: tuple[Discovery, ...]
    evidence_index: dict[str, tuple[DiscoveryEvidence, ...]]
    summary: DiscoverySummary
```

---

## 5. Proposed Package Structure

```
operational/
├── compiler/
│   ├── __init__.py
│   ├── compiler.py                       # OperationalCompiler (existing, unchanged)
│   ├── engineering_discovery_compiler.py  # EngineeringDiscoveryCompiler (existing, unchanged)
│   └── passes/                           # Existing operational passes (unchanged)
│
├── discovery/                            # NEW: Discovery Compiler
│   ├── __init__.py
│   ├── compiler.py                       # DiscoveryCompiler (orchestrator)
│   ├── ir.py                             # DiscoveryIR, Discovery, DiscoveryKind, etc.
│   └── passes/
│       ├── __init__.py
│       ├── base.py                       # DiscoveryPassContext, DiscoveryCompilerPass
│       ├── reachability.py               # Derives discovery statements from reachable_units
│       ├── fan_analysis.py               # Derives from fan_in, fan_out
│       ├── cross_service.py              # Derives from cross_service_references
│       ├── propagation.py                # Derives from execution_depth + dependency_depth
│       ├── validation_gaps.py            # Derives from ValidationModel
│       ├── hidden_relationships.py       # NEW: graph intersection analysis
│       ├── dominant_paths.py             # NEW: frequency analysis on execution chains
│       ├── boundary_invariance.py        # NEW: base vs head entry point diff
│       ├── significance.py               # MOVED from presentation: measurements
│       ├── ranking.py                    # MOVED from presentation: lexicographic ORDER BY
│       ├── surprise.py                   # MOVED from presentation: ratio vectors
│       └── compression.py                # MOVED from presentation: grouping


presentation/
├── compiler/
│   ├── __init__.py
│   ├── compiler.py                       # PresentationCompiler (simplified)
│   └── passes/
│       ├── __init__.py
│       ├── base.py                       # PresentationPassContext (unchanged)
│       ├── ir_import.py                  # NEW: imports DiscoveryIR, converts to PresentationDiscoveries
│       ├── narrative_construction.py     # Existing (unchanged)
│       ├── visual_composition.py         # Existing (unchanged)
│       ├── ir_assembly.py               # Existing (unchanged)
│       └── normalization.py              # Existing (unchanged, but now inputs are DiscoveryIR not EDM directly)
```

---

## 6. Execution Order

### Current Pipeline
```
Repository Compiler → Change Compiler → Behavior Compiler → 
Operational Compiler → Engineering Discovery Compiler → 
Presentation Compiler (9 passes including analysis)
```

### Proposed Pipeline
```
Repository Compiler → Change Compiler → Behavior Compiler → 
Operational Compiler → Engineering Discovery Compiler → 
Discovery Compiler (12+ passes: measurement + graph analysis + ranking + compression)
→ Presentation Compiler (5 passes: import + narrative + visual + assembly)
→ Renderer
```

### Discovery Compiler Pass Order

| Order | Pass | Source Data | Description |
|-------|------|-------------|-------------|
| 1 | **ReachabilityDiscoveryPass** | `BehaviorModel.reachable_units`, `BehaviorModel.execution_chains` | For each changed symbol, emit "reachable from N entry points / reaches M execution units" |
| 2 | **FanAnalysisDiscoveryPass** | `DependencyModel.fan_in`, `DependencyModel.fan_out` | "Symbol X has N upstream callers / M downstream callees" |
| 3 | **CrossServiceDiscoveryPass** | `DependencyModel.cross_service_references` | "Symbol X crosses service boundary: A → B" |
| 4 | **PropagationDiscoveryPass** | `BehaviorModel.execution_depth`, `DependencyModel.dependency_depth` | "Change propagates to depth N (max N service boundaries)" |
| 5 | **ValidationGapDiscoveryPass** | `ValidationModel` + fan-out | "Symbol X (fan-out=N) lacks test coverage" |
| 6 | **HiddenRelationshipDiscoveryPass** | `ReferenceGraph` ∩ `CallGraph` ∩ `EventModel.event_graph` | "Symbol X and Symbol Y are connected via both calls AND events" |
| 7 | **DominantPathDiscoveryPass** | Execution chains, cross-behavior frequency | "Symbol X is traversed by N behaviors (most-shared execution unit)" |
| 8 | **BoundaryInvarianceDiscoveryPass** | Base + head entry points, changed reachable symbols | "Endpoint E reaches changed symbols but its interface is unchanged" |
| 9 | **SignificanceEvaluationPass** | All prior pass outputs | Compute significance metrics for each discovery (MOVED from presentation) |
| 10 | **RankingPass** | Significance metrics | Lexicographic ORDER BY (MOVED from presentation) |
| 11 | **SurpriseDetectionPass** | Change size + impact ratios | Ratio vectors (MOVED from presentation) |
| 12 | **CompressionPass** | Discoveries of same kind | Group related discoveries (MOVED from presentation) |

---

## 7. Minimal Migration Plan

### Phase 1: Create Discovery IR and package structure
1. Create `operational/discovery/` package
2. Create `operational/discovery/ir.py` with `Discovery`, `DiscoveryKind`, `DiscoverySupport`, `DiscoveryEvidence`, `DiscoveryIR`
3. Create `operational/discovery/passes/base.py` with `DiscoveryPassContext`, `DiscoveryCompilerPass`

### Phase 2: Implement passes that derive from existing models
1. Implement passes 1-5 (reachability, fan, cross-service, propagation, validation gaps)
   - Each pass reads from existing models (`BehaviorModel`, `DependencyModel`, etc.)
   - Each pass emits `Discovery` objects with concrete statements
2. Implement passes 6-8 (hidden relationships, dominant paths, boundary invariance)
   - These require NEW graph analysis but use existing graphs

### Phase 3: Move significance, ranking, surprise, compression from presentation
1. Copy `presentation/compiler/passes/significance_evaluation.py` → `operational/discovery/passes/significance.py`
2. Copy `presentation/compiler/passes/ranking.py` → `operational/discovery/passes/ranking.py`
3. Copy `presentation/compiler/passes/surprise_detection.py` → `operational/discovery/passes/surprise.py`
4. Copy `presentation/compiler/passes/compression.py` → `operational/discovery/passes/compression.py`
5. Remove these passes from `PresentationCompiler`

### Phase 4: Wire DiscoveryCompiler into pipeline
1. Add `DiscoveryCompiler` to `runtime/pipeline/pipeline.py`
2. Insert between `_compile_discovery` and `_compile_presentation`
3. EngineeringDiscoveryCompiler output → DiscoveryCompiler → DiscoveryIR
4. Simplify `PresentationCompiler` to import DiscoveryIR instead of running analysis

### Phase 5: Simplify PresentationCompiler
1. Remove normalization pass (or rework to accept DiscoveryIR directly)
2. Add `IRImportPass` that converts `Discovery` objects to `PresentationDiscovery`
3. Keep: narrative construction, visual composition, IR assembly
4. Remove: significance evaluation, ranking, surprise detection, compression

### Phase 6: Remove old imports and cleanup
1. Remove unused imports
2. Update test files
3. Verify PresentationIR output is equivalent (discoveries + narrative + visuals)

---

## 8. Key Design Decisions

### Decision 1: Discovery IR lives in `operational/discovery/`
- Rationale: Discovery is an engineering output, not a presentation concern
- Keeps presentation layer purely about formatting
- Discovery IR is the new contract between "what we found" and "how we show it"

### Decision 2: Discovery passes read from existing models, not raw data
- Each pass accepts `EngineeringDiscoveryModel` (which contains all operational models)
- No pass re-traverses the call graph — they read pre-computed results
- This preserves the "no duplicate traversal" constraint

### Decision 3: Statement generation is deterministic string formatting
- "CustomerWithMembers is reachable from five REST endpoints."
- Template: `"{symbol_name} is reachable from {count} {entry_point_type}(s)."`
- No prose generation — only string templates with interpolated measurements

### Decision 4: Importance is normalized from RankingVector
- Ranking vector from presentation layer provides ordering
- Importance = max_component / total_components (0.0–1.0)
- OR: percentile position within all discoveries (simpler, more stable)

### Decision 5: PresentationCompiler inputs change but output is identical
- `PresentationIR` interface stays the same
- Downstream consumers (renderers, LLM builders) are unaffected
- Only internal pass structure changes

---

## Summary: What Moves Where

| Current Location | Move To | Reason |
|-----------------|---------|--------|
| `presentation/compiler/passes/significance_evaluation.py` | `operational/discovery/passes/significance.py` | Measurement is discovery, not presentation |
| `presentation/compiler/passes/ranking.py` | `operational/discovery/passes/ranking.py` | Ordering is discovery, not presentation |
| `presentation/compiler/passes/surprise_detection.py` | `operational/discovery/passes/surprise.py` | Surprise is discovery, not presentation |
| `presentation/compiler/passes/compression.py` | `operational/discovery/passes/compression.py` | Grouping is discovery, not presentation |
| `presentation/compiler/passes/normalization.py` | Stay (simplified) | Input conversion is presentation concern |
| `presentation/compiler/passes/narrative_construction.py` | Stay | Ordering for human reading is presentation |
| `presentation/compiler/passes/visual_composition.py` | Stay | Semantic-to-renderer mapping is presentation |
| `presentation/compiler/passes/ir_assembly.py` | Stay | Final IR packaging is presentation |
| NEW: `operational/discovery/passes/reachability.py` | New | Derives discovery statements from existing data |
| NEW: `operational/discovery/passes/{fan, cross_service, propagation, hidden_relationships, dominant_paths, boundary_invariance}.py` | New | New deterministic graph analyses |

## Current Pipeline Flow (after migration)

```
Repository Compiler → Change Compiler → Behavior Compiler → 
Operational Compiler → Engineering Discovery Compiler → 
│
├── Discovery Compiler (operational/discovery/compiler.py)
│   ├── 1. ReachabilityDiscoveryPass
│   ├── 2. FanAnalysisDiscoveryPass
│   ├── 3. CrossServiceDiscoveryPass
│   ├── 4. PropagationDiscoveryPass
│   ├── 5. ValidationGapDiscoveryPass
│   ├── 6. HiddenRelationshipDiscoveryPass      [NEW]
│   ├── 7. DominantPathDiscoveryPass            [NEW]
│   ├── 8. BoundaryInvarianceDiscoveryPass      [NEW]
│   ├── 9. SignificanceEvaluationPass           [MOVED]
│   ├── 10. RankingPass                         [MOVED]
│   ├── 11. SurpriseDetectionPass               [MOVED]
│   └── 12. CompressionPass                     [MOVED]
│   │
│   └── Output: DiscoveryIR
│
├── Presentation Compiler (presentation/compiler/compiler.py)
│   ├── 0. IRImportPass                         [NEW: imports DiscoveryIR]
│   ├── 1. NarrativeConstructionPass            [EXISTING]
│   ├── 2. VisualCompositionPass                [EXISTING]
│   └── 3. IRAssemblyPass                       [EXISTING]
│   │
│   └── Output: PresentationIR (unchanged)
│
└── Renderer