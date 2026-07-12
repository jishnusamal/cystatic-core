# Phase 6 — Compiler Stabilization Plan

## Architecture Overview
```
Source Code → Language Adapter → RepositoryModel → ChangeModel → BehaviorModel → OperationalChangeModel
                                  (Public IR 1)    (Public IR 2)  (Public IR 3)   (Public IR 4)
```

## Current Issues
1. **repository/ package** — Already in `language_adapters/model/`, but `repository_compiler` test exists with stale naming
2. **ModelCompiler** — Public in `language_adapters/base/`, but should be private to adapters
3. **Semantic graph** — Leaks outside adapters (test passes raw semantic_graph)
4. **No evidence model** — All models use raw locations without provenance
5. **"Analysis" terminology** — Operational passes use `DependencyAnalysisPass` etc.
6. **"Discovery" terminology** — Behavior discovery pass uses non-compilation terms
7. **Base extractor/parser/normalization** — Need to ensure internals are hidden

## Steps (in order)

### Step 1: Create Evidence Model
- Create `language_adapters/model/evidence.py` with `Evidence`, `FileLocation`, `SymbolReference`, `CallReference`, `ImportReference`, `AnnotationReference`

### Step 2: Add Evidence to RepositoryModel
- Update `Symbol` to carry `evidence: Evidence`
- Update `EntryPoint` to carry `evidence`
- Update `CallEdge` to carry `evidence`
- Update all RepositoryModel types to carry evidence

### Step 3: Add Evidence to ChangeModel
- Update `ModifiedSymbol`, `AddedSymbol`, `RemovedSymbol` with evidence

### Step 4: Add Evidence to BehaviorModel
- Update `Behavior` with evidence
- Update `ExecutionGraph` with evidence on nodes/edges

### Step 5: Add Evidence to OperationalChangeModel
- Update dependency, data, event, api, validation models with evidence

### Step 6: Remove Confidence/Speculative Fields
- Verify no model contains confidence scores

### Step 7: Rename Analysis Passes → Compilation Passes
- `DependencyAnalysisPass` → `DependencyCompilationPass`
- `DataAnalysisPass` → `DataCompilationPass`
- `EventAnalysisPass` → `EventCompilationPass`
- `APIAnalysisPass` → `APICompilationPass`
- `ValidationAnalysisPass` → `ValidationCompilationPass`
- `MetricsPass` → `MetricsCompilationPass`
- `BehaviorDiscoveryPass` → `BehaviorCompilationPass`

### Step 8: Hide Internal IRs
- Make `ModelCompiler` private (`_ModelCompiler`)
- Remove semantic graph exposure from adapter API
- Update tests to not access semantic graph directly

### Step 9: Freeze Public API
- Ensure import paths are clean
- Update all `__init__.py` exports

### Step 10: Update Tests
- Update repository compiler test (rename to adapter test)
- Ensure deterministic testing
- Add evidence verification tests