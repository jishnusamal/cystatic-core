# Runtime Audit Against Compiler Contracts

This document audits the current runtime implementation against the compiler contracts defined in compiler-contracts.md.

## Current Runtime Flow

### Step 1: Repository Model Compilation (Lines 148-220)

**Current Implementation:**
```python
# Line 162-163: Only fetches ONE ref
ref = request.pull_request.head_sha if request.pull_request else request.repository.default_branch
cached_model = await self.repository_store.load(request.repository.full_name, ref)

# Line 182: Fetches only ONE snapshot
snapshot = await self.repository_provider.fetch_repository(request.repository)

# Line 204: Compiles only ONE model
repository_model = adapter.compile(repository_input)

# Line 218-219: Caches with only ONE ref
ref = request.pull_request.head_sha if request.pull_request else request.repository.default_branch
await self.repository_store.save(request.repository.full_name, ref, repository_model)
```

**Expected According to Contract:**
- Should fetch Base snapshot at base_sha
- Should compile RepositoryModel(base)
- Should fetch Head snapshot at head_sha
- Should compile RepositoryModel(head)
- Should cache both models separately

**Status:** ❌ **CRITICAL VIOLATION**
- Only one repository model is created
- No distinction between base and head states
- ChangeCompiler cannot receive different base/head models

---

### Step 2: Diff Fetching (Lines 114-122, 221-252)

**Current Implementation:**
```python
# Line 115-116: Diff is fetched but not used correctly
if context.diff_data is None and request.has_diff:
    context.diff_data = self._diff_snapshot_to_dict(request.diff) if hasattr(request.diff, 'files') else request.diff

# Line 245-248: Diff is fetched between base and head
diff = await self.repository_provider.fetch_diff(
    request.repository,
    request.pull_request.base_sha,
    request.pull_request.head_sha,
)
```

**Expected According to Contract:**
- Diff should be fetched between base_sha and head_sha ✓
- Diff should be passed to ChangeCompiler along with base and head models

**Status:** ⚠️ **PARTIAL**
- Diff fetching is correct
- But diff is not used properly because base/head models are the same

---

### Step 3: Change Compilation (Lines 287-315)

**Current Implementation:**
```python
# Line 305-309: CRITICAL BUG - passes same model for both old and new
context.change_model = self._change_compiler.compile(
    diff_data=context.diff_data,
    old_repository_model=context.repository_model,  # Same as new!
    new_repository_model=context.repository_model,  # Same as old!
)
```

**Expected According to Contract:**
- Should receive RepositoryModel(base) as old_repository_model
- Should receive RepositoryModel(head) as new_repository_model
- Should receive DiffSnapshot

**Status:** ❌ **CRITICAL VIOLATION**
- Both old and new repository models are identical
- ChangeCompiler cannot detect any changes
- Violates ChangeCompiler contract requirement: "Base and Head represent different repository states"

---

### Step 4: Behavior Compilation (Lines 317-343)

**Current Implementation:**
```python
# Line 334-337: Receives only one repository model
context.behavior_model = self._behavior_compiler.compile(
    change_model=context.change_model,
    repository_model=context.repository_model,  # Which one? Base or Head?
)
```

**Expected According to Contract:**
- Should receive RepositoryModel(head) - the current state
- Should receive ChangeModel

**Status:** ⚠️ **PARTIAL**
- Receives a repository model, but unclear if it's head or base
- Should explicitly be the head model per contract

---

### Step 5: Operational Compilation (Lines 345-375)

**Current Implementation:**
```python
# Line 365-369: Receives only one repository model
context.ocm = self._operational_compiler.compile(
    repository_model=context.repository_model,  # Which one?
    change_model=context.change_model,
    behavior_model=context.behavior_model,
)
```

**Expected According to Contract:**
- Should receive RepositoryModel(head)
- Should receive ChangeModel
- Should receive BehaviorModel

**Status:** ⚠️ **PARTIAL**
- Same issue as BehaviorCompiler - unclear which model is passed

---

## PipelineContext Issues

**Current Implementation:**
```python
# Line 34: Only ONE repository model field
repository_model: RepositoryModel | None = None
```

**Expected According to Contract:**
- Should have separate fields for base and head repository models
- Should have separate fields for base and head repository snapshots
- Models should be immutable once set

**Status:** ❌ **VIOLATION**
- Cannot track both base and head states
- No way to ensure correct model is passed to each compiler

---

## RepositoryStore Issues

**Current Implementation:**
```python
# Line 162-163: Only loads one model
ref = request.pull_request.head_sha if request.pull_request else request.repository.default_branch
cached_model = await self.repository_store.load(request.repository.full_name, ref)

# Line 218-219: Only saves one model
ref = request.pull_request.head_sha if request.pull_request else request.repository.default_branch
await self.repository_store.save(request.repository.full_name, ref, repository_model)
```

**Expected According to Contract:**
- Should load/cache models by (repository, commit_sha)
- Should separately cache base and head models
- Should compile if missing, then cache

**Status:** ⚠️ **PARTIAL**
- Cache key structure is correct: (repository, ref)
- But only one model is ever cached per execution
- Should cache both base and head models

---

## Summary of Violations

| Component | Violation | Severity | Impact |
|-----------|-----------|----------|--------|
| Pipeline.run() | Only compiles one repository model | CRITICAL | Cannot detect changes |
| _ensure_repository_model() | Only fetches head snapshot | CRITICAL | No base state for comparison |
| _compile_change() | Passes same model for old and new | CRITICAL | ChangeCompiler cannot work |
| PipelineContext | Only one repository_model field | HIGH | Cannot track base/head separately |
| BehaviorCompiler call | Unclear which model is passed | MEDIUM | Should explicitly be head |
| OperationalCompiler call | Unclear which model is passed | MEDIUM | Should explicitly be head |

## Root Cause

The fundamental issue is that the runtime was designed to compile only ONE repository model (the head state), but the ChangeCompiler contract requires TWO different models (base and head) to detect changes.

This is a **design mismatch** between the runtime and the compiler contracts.

## Required Changes

1. **Phase 3**: Update PipelineContext to have separate base/head fields
2. **Phase 4**: Modify _ensure_repository_model to compile both base and head
3. **Phase 6**: Update ChangeCompiler to accept a dedicated input model
4. **Phase 7**: Add invariant validation before each compiler call
5. **Phase 5**: Ensure RepositoryStore properly caches both models

## Verification

The current implementation cannot possibly work correctly because:
- ChangeCompiler receives identical models for base and head
- No changes can be detected when comparing a model to itself
- All downstream compilers receive empty/incorrect change data