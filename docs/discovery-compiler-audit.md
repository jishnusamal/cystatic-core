# Discovery Compiler Audit

## 1. Existing Reusable Compiler Passes

| Desired Capability | Exists | Partial | Missing | Implementation Path | Reusable Pass | Reusable Model | Reusable Graph | Reuse Strategy |
|-------------------|--------|---------|---------|---------------------|---------------|----------------|----------------|-----------------|
| Reachability | ✅ | | | `behavior/compiler/passes/reachable_units/` | ReachableUnitsPass | BehaviorModel.reachable_units | ExecutionGraph | Direct reuse |
| Execution Chains | ✅ | | | `behavior/compiler/passes/execution_chain/` | ExecutionChainPass | BehaviorModel.execution_chains | ExecutionChain | Direct reuse |
| Shared Execution | ✅ | | | `behavior/compiler/passes/shared_execution/` | SharedExecutionPass | BehaviorModel.shared_executions | SharedExecutionGraph | Direct reuse |
| Fan-In | ✅ | | | `operational/compiler/passes/dependency/` | DependencyPass | DependencyModel.fan_in | DependencyGraph | Direct reuse |
| Fan-Out | ✅ | | | `operational/compiler/passes/dependency/` | DependencyPass | DependencyModel.fan_out | DependencyGraph | Direct reuse |
| Cross-Service References | ✅ | | | `operational/compiler/passes/dependency/` | DependencyPass | DependencyModel.cross_service_references | ServiceBoundaryGraph | Direct reuse |
| Execution Depth | ✅ | | | `behavior/compiler/passes/execution_chain/` | ExecutionChainPass | BehaviorModel.execution_depth | ExecutionGraph | Direct reuse |
| Entry Points | ✅ | | | `behavior/compiler/passes/entry_point/` | EntryPointPass | BehaviorModel.entry_points | ControlFlowGraph | Direct reuse |
| Terminal Points | ✅ | | | `behavior/compiler/passes/terminal_point/` | TerminalPointPass | BehaviorModel.terminal_points | ControlFlowGraph | Direct reuse |
| API Surface | ✅ | | | `operational/compiler/passes/api/` | APIPass | APIModel | APIGraph | Direct reuse |
| Event Propagation | ✅ | | | `operational/compiler/passes/events/` | EventPass | EventModel | EventGraph | Direct reuse |
| Data Propagation | ✅ | | | `operational/compiler/passes/data/` | DataPass | DataModel | DataGraph | Direct reuse |
| Validation Gaps | ✅ | | | `operational/compiler/passes/validation/` | ValidationPass | ValidationModel | CoverageGraph | Direct reuse |
| Dependency Traversal | ✅ | | | `operational/compiler/passes/dependency/` | DependencyPass | DependencyModel | DependencyGraph | Direct reuse |
| Ranking | | ✅ | | `presentation/compiler/passes/ranking.py` | RankingPass | SignificanceMetrics → RankingVector | N/A | MOVE to Discovery |
| Surprise Detection | | ✅ | | `presentation/compiler/passes/surprise_detection.py` | SurpriseDetectionPass | SurpriseVector | N/A | MOVE to Discovery |
| Significance Evaluation | | ✅ | | `presentation/compiler/passes/significance_evaluation.py` | SignificanceEvaluationPass | SignificanceMetrics | N/A | MOVE to Discovery |
| Compression | | ✅ | | `presentation/compiler/passes/compression.py` | CompressionPass | N/A (grouping logic) | N/A | MOVE to Discovery |
| Hidden Relationships | | | ✅ | NEW PASS NEEDED | HiddenRelationshipPass | BehaviorModel | ExecutionGraph + APIModel | CREATE |
| Dominant Execution | | | ✅ | NEW PASS NEEDED | DominantExecutionPass | DependencyModel + BehaviorModel | DependencyGraph + ExecutionGraph | CREATE |
| Boundary Invariants | | | ✅ | NEW PASS NEEDED | BoundaryInvariantPass | ChangeModel + APIModel + DependencyModel | ServiceBoundaryGraph | CREATE |
| Validation Gap Expression | | | ✅ | NEW PASS NEEDED | ValidationGapPass | ValidationModel + BehaviorModel | ExecutionChain | CREATE |

## 2. Mapping: Existing Passes → Discovery Passes

### Direct Reuse (No Changes Needed)
These passes already produce the right data. Discovery Compiler will read their outputs:

| Discovery Pass | Reads From | Existing Pass |
|---------------|-----------|---------------|
| HiddenRelationshipPass | BehaviorModel.entry_points, execution_chains | EntryPointPass, ExecutionChainPass |
| HiddenRelationshipPass | BehaviorModel.behaviors | BehaviorDiscoveryPass |
| DominantExecutionPass | DependencyModel.fan_in, fan_out | DependencyPass |
| DominantExecutionPass | BehaviorModel.reachable_units | ReachableUnitsPass |
| DominantExecutionPass | BehaviorModel.execution_depth | ExecutionChainPass |
| BoundaryInvariantPass | ChangeModel.added/removed/modified | ChangeClassificationPass |
| BoundaryInvariantPass | APIModel.rest, graphql, rpc | APIPass |
| BoundaryInvariantPass | DependencyModel.cross_service_references | DependencyPass |
| ValidationGapPass | ValidationModel.unit_tests, integration_tests, e2e_tests | ValidationPass |
| ValidationGapPass | BehaviorModel.execution_chains | ExecutionChainPass |
| SharedExecutionPass | BehaviorModel.shared_executions | SharedExecutionPass (direct reuse) |

### Moves from Presentation to Discovery
These passes perform deterministic computation and belong in Discovery:

| Current Location | Pass | Why It Moves |
|-----------------|------|--------------|
| `presentation/compiler/passes/significance_evaluation.py` | SignificanceEvaluationPass | Computes raw measurements from model - deterministic |
| `presentation/compiler/passes/ranking.py` | RankingPass | Lexicographic ORDER BY - deterministic, no prose |
| `presentation/compiler/passes/surprise_detection.py` | SurpriseDetectionPass | Ratio computation - deterministic, no heuristics |
| `presentation/compiler/passes/compression.py` | CompressionPass | Grouping logic - deterministic, no rendering |

## 3. Missing Discovery Passes

### 3.1 HiddenRelationshipPass
**Purpose:** Reveal non-obvious relationships between changed symbols and execution paths

**Inputs:**
- BehaviorModel.entry_points (where execution begins)
- BehaviorModel.execution_chains (ordered execution paths)
- BehaviorModel.behaviors (affected behavioral units)

**Outputs:**
- Discoveries like: "CustomerWithMembers is reachable from 5 REST endpoints"
- Discoveries like: "Checkout.confirm() reaches BillingService through 12 execution units"

**Algorithm:**
1. For each entry point, trace execution chain
2. Count reachable units per entry point
3. Identify indirect paths (entry → chain → terminal)
4. Emit discovery with complete statement

**Reuse:** EntryPointPass, ExecutionChainPass outputs

### 3.2 DominantExecutionPass
**Purpose:** Identify symbols with greatest execution reach

**Inputs:**
- DependencyModel.fan_in (upstream callers)
- DependencyModel.fan_out (downstream callees)
- BehaviorModel.reachable_units (execution reach)
- BehaviorModel.execution_depth (propagation depth)

**Outputs:**
- Discoveries like: "CustomerRepository.load() is referenced by 39 upstream callers"
- Discoveries like: "The deepest execution path spans 33 calls"

**Algorithm:**
1. Sort symbols by fan-in descending
2. Take top N (e.g., top 5)
3. Emit discovery with fan-in count
4. Identify max execution depth
5. Emit discovery with depth

**Reuse:** DependencyPass, ReachableUnitsPass outputs

### 3.3 BoundaryInvariantPass
**Purpose:** Highlight important boundaries that remain unchanged

**Inputs:**
- ChangeModel (what changed)
- APIModel (external surface)
- DependencyModel.cross_service_references (service boundaries)

**Outputs:**
- Discoveries like: "505 internal symbols changed without modifying the public REST API"
- Discoveries like: "No service boundaries were crossed"

**Algorithm:**
1. Count total changed symbols
2. Count API endpoints (rest, graphql, rpc)
3. If changed > 0 and API unchanged → emit discovery
4. Count cross-service references
5. If cross-service == 0 and changed > 0 → emit discovery

**Reuse:** ChangeClassificationPass, APIPass, DependencyPass outputs

### 3.4 ValidationGapPass
**Purpose:** Express missing validation in terms of execution paths

**Inputs:**
- ValidationModel (test coverage)
- BehaviorModel.execution_chains (execution paths)
- DependencyModel.fan_out (for weighting)

**Outputs:**
- Discoveries like: "The Checkout → Billing execution path (8 units) has no end-to-end validation"
- Discoveries like: "CustomerRepository.load() (fan-out=12) has no integration test coverage"

**Algorithm:**
1. For each execution chain, check if e2e tests exist
2. If no e2e and path length >= 3 → emit discovery
3. For high fan-out symbols, check integration tests
4. If no integration tests → emit discovery

**Reuse:** ValidationPass, ExecutionChainPass outputs

## 4. Proposed Discovery IR

### Design Principles
1. **Complete statements** - Every discovery has a natural-language statement
2. **Evidence-backed** - Every claim has traceable evidence
3. **No rendering info** - No markdown, HTML, GitHub formatting
4. **Immutable** - Frozen dataclasses
5. **Deterministic** - Same inputs → same outputs

### Schema

```python
@dataclass(frozen=True)
class Discovery:
    id: str                           # Stable identifier
    kind: DiscoveryKind               # Semantic classification
    statement: str                    # Complete natural-language statement
    importance: float                 # 0.0 to 1.0 (set by RankingPass)
    support: DiscoverySupport         # Raw measurements
    evidence: tuple[DiscoveryEvidence, ...]  # Traceable evidence
    metadata: dict[str, Any]          # Additional structured data

@dataclass(frozen=True)
class DiscoverySupport:
    # Core measurements
    execution_reach: int              # How many behaviors affected
    fan_in: int                       # Upstream callers
    fan_out: int                      # Downstream callees
    propagation_depth: int            # Max execution depth
    boundary_crossings: int           # Architectural boundaries crossed
    
    # Surface areas
    external_surface: int             # API endpoints affected
    data_surface: int                 # Data entities affected
    event_surface: int                # Events affected
    validation_coverage: int          # Covered paths
    validation_gaps: int              # Uncovered paths
    
    # Coupling
    shared_by_count: int              # Behaviors sharing this symbol
    cross_service_count: int          # Service boundaries crossed
    
    # Change context
    changed_symbol_count: int         # Total changed symbols
    changed_file_count: int           # Total changed files
    
    # [MOVED FROM PRESENTATION] Ranking and surprise
    ranking_vector: tuple[int, ...]   # Lexicographic ORDER BY components
    surprise_ratios: dict[str, float] # Deterministic ratio vectors

@dataclass(frozen=True)
class DiscoveryEvidence:
    source: str                       # Compiler stage ("behavior", "operational", "change")
    source_id: str                    # Stable identifier in that stage
    description: str                  # Human-readable description
    evidence_ref: str                 # URI to underlying artifact

@dataclass(frozen=True)
class DiscoveryIR:
    metadata: DiscoveryMetadata       # Compiler version, timestamp, counts
    discoveries: tuple[Discovery, ...]  # Ordered by importance descending
    summary: DiscoverySummary         # Aggregate counts
    evidence_index: dict[str, tuple[DiscoveryEvidence, ...]]  # Fast lookup
```

### Discovery Kinds
```python
class DiscoveryKind(str, Enum):
    HIDDEN_RELATIONSHIP = "hidden_relationship"
    DOMINANT_EXECUTION = "dominant_execution"
    BOUNDARY_INVARIANT = "boundary_invariant"
    VALIDATION_GAP = "validation_gap"
    SHARED_EXECUTION = "shared_execution"
    CROSS_SERVICE = "cross_service"
    PROPAGATION = "propagation"
    FAN_IN = "fan_in"
    FAN_OUT = "fan_out"
    EXECUTION_DEPTH = "execution_depth"
    API_SURFACE = "api_surface"
    EVENT_PROPAGATION = "event_propagation"
    DATA_PROPAGATION = "data_propagation"
    SURPRISE = "surprise"
    COMPRESSED = "compressed"
```

## 5. Proposed Package Structure

```
operational/discovery/
├── __init__.py                 # Exports DiscoveryCompiler
├── compiler.py                 # DiscoveryCompiler orchestrator
├── model.py                    # Discovery IR models (Discovery, DiscoveryIR, etc.)
├── passes/
│   ├── __init__.py
│   ├── base.py                 # DiscoveryPassContext, DiscoveryCompilerPass
│   ├── hidden_relationship.py  # NEW: Reveal non-obvious relationships
│   ├── dominant_execution.py   # NEW: Greatest execution reach
│   ├── boundary_invariant.py   # NEW: Unchanged boundaries
│   ├── validation_gap.py       # NEW: Missing validation
│   ├── shared_execution.py     # REUSE: Convert existing shared execution data
│   ├── significance.py         # MOVED FROM presentation: Raw measurements
│   ├── ranking.py              # MOVED FROM presentation: Lexicographic ORDER BY
│   ├── surprise.py             # MOVED FROM presentation: Ratio vectors
│   └── compression.py          # MOVED FROM presentation: Group related
```

## 6. Execution Order

### Discovery Compiler Passes (9 passes)

```python
class DiscoveryCompiler:
    def __init__(self):
        self.passes = [
            HiddenRelationshipPass(),       # Pass 1: Non-obvious relationships
            DominantExecutionPass(),         # Pass 2: Greatest execution reach
            BoundaryInvariantPass(),         # Pass 3: Unchanged boundaries
            ValidationGapPass(),             # Pass 4: Missing validation
            SharedExecutionPass(),           # Pass 5: Shared infrastructure
            SignificanceEvaluationPass(),    # Pass 6: Raw measurements [MOVED]
            RankingPass(),                   # Pass 7: Lexicographic ORDER BY [MOVED]
            SurpriseDetectionPass(),         # Pass 8: Ratio vectors [MOVED]
            CompressionPass(),               # Pass 9: Group related [MOVED]
        ]
```

**Ordering rationale:**
1. **Discovery passes first** (1-5): Emit complete statements with evidence
2. **Measurement passes second** (6): Populate support fields from model
3. **Ranking pass third** (7): Assign importance based on support
4. **Surprise pass fourth** (8): Boost importance for surprising discoveries
5. **Compression pass last** (9): Group similar discoveries after ranking

### Pipeline Integration

```
Repository Compiler
    ↓
Change Compiler
    ↓
Behavior Compiler
    ↓
Operational Compiler
    ↓
Engineering Discovery Compiler (produces EngineeringDiscoveryModel)
    ↓
Discovery Compiler (NEW - produces DiscoveryIR)
    ↓
Presentation Compiler (UPDATED - consumes DiscoveryIR, produces PresentationIR)
    ↓
Renderers (GitHub, JSON, LLM)
```

### Pipeline Steps (Updated)

```python
# Step 1: Repository compilation (unchanged)
# Step 2: Diff fetching (unchanged)
# Step 3: Change compilation (unchanged)
# Step 4: Behavior compilation (unchanged)
# Step 5: Operational compilation (unchanged)
# Step 6: Engineering discovery model compilation (unchanged)
# Step 7: Discovery IR compilation (NEW)
context.discovery_ir = DiscoveryCompiler().compile(context.edm)
# Step 8: Presentation IR compilation (UPDATED)
context.presentation_ir = PresentationCompiler().compile(context.discovery_ir)
```

## 7. Minimal Migration Plan

### Phase 1: Create Discovery Compiler (NEW)
**Goal:** Build the Discovery Compiler without breaking existing system

**Steps:**
1. Create `operational/discovery/` package structure
2. Implement `DiscoveryIR` model (model.py)
3. Implement base classes (passes/base.py)
4. Implement 5 new discovery passes (hidden_relationship, dominant_execution, boundary_invariant, validation_gap, shared_execution)
5. Implement DiscoveryCompiler orchestrator (compiler.py)
6. Update PipelineContext with `discovery_ir` field
7. Wire DiscoveryCompiler into pipeline as Step 7
8. **Keep PresentationCompiler unchanged** - it still consumes EngineeringDiscoveryModel

**Verification:**
- Discovery Compiler runs successfully
- Presentation Compiler still works (backward compatible)
- No existing tests broken

### Phase 2: Move Deterministic Passes (MOVE)
**Goal:** Move significance, ranking, surprise, compression from Presentation to Discovery

**Steps:**
1. Create `operational/discovery/passes/significance.py` (moved from presentation)
2. Create `operational/discovery/passes/ranking.py` (moved from presentation)
3. Create `operational/discovery/passes/surprise.py` (moved from presentation)
4. Create `operational/discovery/passes/compression.py` (moved from presentation)
5. Update DiscoveryCompiler to include these 4 passes
6. Update DiscoveryIR model to include ranking_vector and surprise_ratios
7. **Keep old presentation passes as deprecated** (don't delete yet)

**Verification:**
- Discovery Compiler now has 9 passes
- DiscoveryIR includes ranking and surprise data
- Old presentation passes still exist (but unused)

### Phase 3: Update Presentation Compiler (CONSUME DiscoveryIR)
**Goal:** Make Presentation Compiler consume DiscoveryIR instead of EngineeringDiscoveryModel

**Steps:**
1. Update `PresentationCompiler.compile()` signature to accept `DiscoveryIR`
2. Update `PresentationPassContext` to use `discovery_ir` field
3. Update NormalizationPass to pass through Discovery objects (no more model walking)
4. Update DiscoveryExtractionPass to convert Discovery → PresentationDiscovery
5. Remove SignificanceEvaluationPass, RankingPass, SurpriseDetectionPass, CompressionPass from PresentationCompiler
6. Update pipeline to pass `discovery_ir` to PresentationCompiler

**Verification:**
- Presentation Compiler consumes DiscoveryIR
- Presentation Compiler has only 5 passes (normalization, extraction, narrative, visual, assembly)
- No discovery logic in Presentation Compiler
- All existing tests pass

### Phase 4: Cleanup (FINAL)
**Goal:** Remove deprecated code

**Steps:**
1. Delete old presentation passes (significance_evaluation.py, ranking.py, surprise_detection.py, compression.py)
2. Remove deprecated imports
3. Update documentation
4. Run full test suite

**Verification:**
- All tests pass
- No broken imports
- Documentation updated

## Key Design Decisions

### Why Move Significance/Ranking/Surprise/Compression?
These passes perform **deterministic computation**, not presentation:
- **Significance**: Reads model data, populates measurements (no prose)
- **Ranking**: Lexicographic ORDER BY (no weights, no ML)
- **Surprise**: Ratio computation (no heuristics)
- **Compression**: Grouping logic (no rendering)

They belong in the Discovery Compiler where all deterministic analysis lives.

### Why Keep Presentation Compiler?
The Presentation Compiler still has important responsibilities:
- **Narrative Construction**: Assign narrative positions (ordering for humans)
- **Visual Composition**: Assign semantic visuals (renderer chooses format)
- **IR Assembly**: Assemble final PresentationIR

These are presentation concerns, not discovery concerns.

### Why Not Delete Old Passes Immediately?
- **Backward compatibility**: Existing code may reference them
- **Gradual migration**: Allows testing each phase independently
- **Safety**: Easy rollback if issues found

## Constraints Satisfied

✅ **Preserve existing architecture** - Reuse existing compiler outputs
✅ **No duplicate graph traversal** - All passes read pre-computed models
✅ **No AI in deterministic stages** - All computation is pure Python
✅ **Keep compiler stages pure** - Clear input/output contracts
✅ **Complete statements** - Every discovery has natural-language statement
✅ **Evidence-backed** - Every claim has traceable evidence
✅ **No rendering in Discovery IR** - No markdown, HTML, GitHub formatting