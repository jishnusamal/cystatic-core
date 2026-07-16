# Compiler Contracts

This document defines the formal contracts for each compiler phase in the factor-api pipeline.

## RepositoryCompiler

**Input:**
- RepositorySnapshot (repository files and metadata)

**Output:**
- RepositoryModel

**Invariants:**
- Represents exactly one immutable repository snapshot at a specific commit
- All symbols, call graphs, and reference graphs are derived from the snapshot
- Language detection is performed and stored in metadata
- Model is immutable once created

**Failure Conditions:**
- Language detection fails
- Adapter compilation fails
- Snapshot is empty or invalid

---

## ChangeCompiler

**Input:**
- RepositoryModel(base) - repository state before changes
- RepositoryModel(head) - repository state after changes
- DiffSnapshot - git diff between base and head

**Output:**
- ChangeModel

**Invariants:**
- Base and Head represent different repository states (different SHAs)
- All changed symbols are identified by comparing base and head models
- Diff is used for line-level change details
- Every modified symbol has a corresponding entry in the diff
- Base and Head models are never modified

**Failure Conditions:**
- Base model is None
- Head model is None
- Diff data is None or invalid
- Base SHA == Head SHA (unless intentionally analyzing identical revisions)

---

## BehaviorCompiler

**Input:**
- RepositoryModel(head) - current repository state
- ChangeModel - detected changes

**Output:**
- BehaviorModel

**Invariants:**
- Every discovered behavior originates from one or more changed symbols
- Execution graphs trace from changed symbols through the call graph
- Only behaviors affected by changes are discovered
- RepositoryModel is the head state (current state after changes)

**Failure Conditions:**
- RepositoryModel is None
- ChangeModel is None
- No changed symbols to trace from

---

## OperationalCompiler

**Input:**
- RepositoryModel(head) - current repository state
- ChangeModel - detected changes
- BehaviorModel - affected behaviors

**Output:**
- OperationalChangeModel

**Invariants:**
- Every operational artifact is traceable back to discovered behaviors
- All enrichment (dependencies, events, APIs, etc.) is derived from the three input models
- Consistency validation ensures all references are valid
- Output is immutable and complete

**Failure Conditions:**
- RepositoryModel is None
- ChangeModel is None
- BehaviorModel is None
- Consistency validation fails (invalid references)

---

## EngineeringDiscoveryCompiler

**Input:**
- OperationalChangeModel - the composed and enriched operational model

**Output:**
- EngineeringDiscoveryModel

**Invariants:**
- All data is projected from the OperationalChangeModel (no new analysis)
- Execution-oriented abstractions are extracted from the behavior model
- Enrichment models (dependency, data, event, api, validation, metrics) are preserved
- The model uses semantic section names, not presentation terminology
- Output is immutable and deterministic

**Failure Conditions:**
- OperationalChangeModel is missing required repository, change, or behavior models

---

## Pipeline Flow

```
RepositorySnapshot(base)
        ↓
RepositoryModel(base) [immutable]

RepositorySnapshot(head)
        ↓
RepositoryModel(head) [immutable]

RepositoryModel(base) + RepositoryModel(head) + DiffSnapshot
        ↓
ChangeCompiler
        ↓
ChangeModel

RepositoryModel(head) + ChangeModel
        ↓
BehaviorCompiler
        ↓
BehaviorModel

RepositoryModel(head) + ChangeModel + BehaviorModel
        ↓
OperationalCompiler
        ↓
OperationalChangeModel

OperationalChangeModel
        ↓
EngineeringDiscoveryCompiler
        ↓
EngineeringDiscoveryModel (Canonical IR)
        ↓
Renderer (GitHub, Slack, Dashboard, API, LLM)
```

## Key Principles

1. **Immutability**: Once a model is created, it is never modified
2. **Explicit Inputs**: Every compiler receives exactly what its contract specifies
3. **Determinism**: Same inputs always produce same outputs
4. **Traceability**: Every artifact can be traced back to its source
5. **Validation**: Each compiler validates its inputs before execution
6. **Separation of Concerns**: Compilers produce models; renderers produce presentation