# Memory Architecture

> **Scope** – This document traces memory allocation and object lifetime from the moment
> a GitHub PR is received by `/v1/analyze` to the moment the LLM response is returned.
> All claims cite exact source files and line numbers. No inferences are made where code
> can be read directly.
>
> **Observed baselines** (from profiling):
>
> | Repository | Start RSS | After source load | After SemanticCompiler | After clone (L513) | LLM sent |
> |---|---|---|---|---|---|
> | Polar (~3 k files) | ~80 MB | ~251 MB | ~280 MB | ~560 MB | ~420 MB |
> | PostHog (~8 k files) | ~80 MB | ~850 MB | ~940 MB | ~1 880 MB | ~1 100 MB |

---

## Table of Contents

1. [Pipeline Stage Map](#1-pipeline-stage-map)
2. [Source Loading — `fetch_repository_at_sha`](#2-source-loading)
3. [AST Lifetime — `FileContext` and `_build_index`](#3-ast-lifetime)
4. [Symbol Model — `SymbolEntry` → `Symbol`](#4-symbol-model)
5. [Import Resolution — `SemanticCompiler` Stage 2](#5-import-resolution)
6. [Call Graph Construction — `SemanticCompiler` Stage 3](#6-call-graph-construction)
7. [`RepositoryGraph` — Structure and Indexes](#7-repositorygraph)
8. [`pipeline.py:513` — The pickle Clone](#8-pipelinepy513-the-pickle-clone)
9. [`semantic_compiler.py` Hotspots](#9-semantic_compilerpy-hotspots)
10. [`GraphPatcher` — Incremental Patching](#10-graphpatcher)
11. [`RepositoryGraph.clone()` vs `to_model()`](#11-repositorygraphclone-vs-to_model)
12. [`RepositoryModel` — Immutable Snapshot](#12-repositorymodel)
13. [Downstream Compilers](#13-downstream-compilers)
14. [LLM Context Construction](#14-llm-context-construction)
15. [Object Duplication Map](#15-object-duplication-map)
16. [Ownership and Lifetime Table](#16-ownership-and-lifetime-table)
17. [Scaling Characteristics](#17-scaling-characteristics)
18. [Memory vs. Performance Trade-offs](#18-memory-vs-performance-trade-offs)
19. [Data Requirements — What Must Stay vs. What Can Be Released](#19-data-requirements)
20. [Top Memory Drivers Summary](#20-top-memory-drivers-summary)
21. [Open Questions](#21-open-questions)

---

## 1. Pipeline Stage Map

```
/v1/analyze  (api/routes/github.py:185)
│
├── MemoryProfiler.log_memory("Start of request")   # RSS baseline
│
├── pipeline.run(analysis_request)
│   │
│   ├─ [1] _compile_repository()   (pipeline.py ~L300–560)
│   │   ├─ fetch_repository_at_sha(base_sha)        # zipball download → dict[str, str]
│   │   ├─ adapter.compile_graph(base_snapshot)     # full compile: RepositoryIndex → RepositoryGraph
│   │   │   ├─ _build_index(files)                  # parse ASTs, run indexing passes → RepositoryIndex
│   │   │   └─ semantic_compiler.compile(index)     # resolve → RepositoryModel
│   │   ├─ repository_store.save(base_sha, base_graph)   # pickle to disk
│   │   │
│   │   ├─ fetch_repository_at_sha(head_sha)        # SECOND zipball download
│   │   ├─ fetch diff (changed_files_dict only)
│   │   │
│   │   ├─ pickle.loads(pickle.dumps(base_graph))   # ← pipeline.py:513  PEAK MEMORY
│   │   │
│   │   ├─ adapter.compile_incremental(patched_graph, changed_files)
│   │   │   └─ GraphPatcher.patch(base_graph, changed_files)
│   │   │
│   │   └─ patched_graph.to_model()                 # RepositoryGraph → RepositoryModel
│   │
│   ├─ [2] _compile_change()       → ChangeModel
│   ├─ [3] _compile_behavior()     → BehaviorModel
│   ├─ [4] _compile_operational()  → OperationalChangeModel
│   ├─ [5] _compile_discovery()    → EngineeringDiscoveryModel
│   ├─ [6] _compile_discovery_ir() → DiscoveryIR
│   ├─ [7] _compile_review_context() → ReviewContext
│   └─ [8] _compile_llm_context()  → LLMContext
│
├─ pipeline.generate_llm_comment()  # LLM API request
└─ return JSONResponse
```

All artifacts accumulate in a single `PipelineContext` dataclass
(`engine/pipeline/context.py:25`) that holds references to every intermediate model for
the lifetime of the request. Nothing is released until the request handler returns.

---

## 2. Source Loading

**File**: `integrations/github/repositories.py`  
**Method**: `fetch_repository_at_sha`

```python
# L107-114
content_bytes = bytearray()
for chunk in response.iter_content(chunk_size=1024 * 1024):
    if chunk:
        content_bytes.extend(chunk)
zip_content = bytes(content_bytes)
```

A `bytearray` is grown incrementally (1 MB chunks), then converted to an immutable
`bytes` object. Both live simultaneously at the conversion boundary:
**peak during download ≈ 2 × zip_content_size**.

```python
# L126-162
with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
    for name in all_names:
        raw = zf.read(name)
        content = raw.decode("utf-8")
        files[relative_name] = content  # dict[str, str]
```

`io.BytesIO(zip_content)` wraps (does not copy) `zip_content`. Each `zf.read(name)` is
a temporary `bytes`; after `decode` the `bytes` is released but the `str` persists in
`files`. At peak during extraction: `zip_content + io.BytesIO wrapper + files dict`.

The returned `RepositorySnapshot.files` remains alive in
`PipelineContext.base_repository_snapshot` for the full request lifetime.

**Memory equation at end of source loading:**

```
RSS Δ ≈ zip_bytes + Σ(decoded_source_strings)
       ≈ compressed_size + uncompressed_source_size
```

For Polar: 80 MB → 251 MB (Δ ≈ 171 MB = ~80 MB zip + ~90 MB decoded source strings).

---

## 3. AST Lifetime

**File**: `engine/language/python/adapter.py`  
**Method**: `_build_index`

```python
# L162-176
tree = ast.parse(content, filename=file_path)
context = FileContext(
    path=file_path,
    source=content,  # ← reference to the str already in files dict
    ast=tree,
    language=language,
)
file_contexts.append(context)
```

`FileContext` (`engine/language/base/file_context.py`) uses `__slots__` (memory-efficient),
but **all `file_contexts` are accumulated in a list before any indexing pass runs** (see
`compile_with_visitor`), meaning N ASTs are live simultaneously.

A Python AST for a 10 000-line file is typically 3–8 MB of `ast.*` node objects.

After `compile_with_visitor` returns, `file_contexts` goes out of scope and ASTs become
eligible for GC. Python's cyclic GC does not guarantee immediate reclamation for large
object graphs; AST memory may be retained until the first major GC cycle after compilation.

**Key observation**: `source` inside `FileContext` is the *same str object* already in
`RepositorySnapshot.files`. No duplication of source text occurs.

---

## 4. Symbol Model

**Index entry**: `engine/repository/model/repository_index.py`  
**Model symbol**: `engine/repository/model/symbol.py`

The pipeline maintains two representations of every symbol simultaneously during
`SemanticCompiler._compile_impl`:

| Layer | Type | Mutability | Contains |
|---|---|---|---|
| `SymbolEntry` (index) | `@dataclass(frozen=True)` | immutable | raw strings: name, kind, visibility, range tuple, properties dict |
| `Symbol` (model) | `@dataclass(frozen=True)` | immutable | same + `Evidence` with `FileLocation` + constructed id string |

`symbol_index: dict[str, Symbol]` and `symbols: list[Symbol]` hold the **same Symbol
objects** — no duplication. `name_to_symbols: dict[str, list[Symbol]]` also holds
references to the same objects.

After `RepositoryModel(symbols=frozenset(symbols), ...)` is constructed, the lists and
dicts are released. The `frozenset` holds the only remaining strong references.

Each `Symbol` carries an `Evidence` with a `FileLocation` (5 fields). For a repo with
10 000 symbols: 10 000 `Symbol` + 10 000 `Evidence` + 10 000 `FileLocation` objects.

---

## 5. Import Resolution

**File**: `engine/language/base/semantic_compiler.py`  
**Stage 2** (`_compile_impl` L192–224)

```python
# Build name index ONCE for O(1) lookups
name_to_symbols: dict[str, list[Symbol]] = {}
for sym_id, symbol in symbol_index.items():
    name_to_symbols.setdefault(symbol.name, []).append(symbol)

for idx, imp_sym in enumerate(import_symbols):
    self._resolve_import_references_fast(imp_sym, name_to_symbols, reference_edges)
```

`reference_edges: list[ReferenceEdge]` grows by one `ReferenceEdge` per resolved import.
Each `ReferenceEdge` is a frozen dataclass carrying two id strings and an optional
`Evidence`.

For a 3 000-file Python repo (20 000–80 000 imports): roughly 5–20 MB of frozen
dataclass instances.

`name_to_symbols` is temporary — released when Stage 2 completes.

---

## 6. Call Graph Construction

**File**: `engine/language/base/semantic_compiler.py`  
**Stage 3** (`_compile_impl` L227–362)

Five additional lookup tables are built at Stage 3 start:

```python
callee_name_to_ids: dict[str, list[str]] = {}  # name → list of symbol IDs
resolved_imports: dict[tuple[str, str], str] = {}  # (file, name) → target_id
file_symbol_map: dict[tuple[str, str], Symbol] = {}
class_method_map: dict[tuple[str, str, str], Symbol] = {}
resolved_inheritance_map: dict[str, list[str]] = {}
```

All five are local to `_compile_impl` — released when the method returns. They do not
allocate new strings, only tuple keys referencing existing id strings.

`call_edges: list[CallEdge]` grows by one `CallEdge` per resolved call. Each `CallEdge`
carries two id strings + `Evidence` + `FileLocation`. For PostHog (~8 k files) with
200 000+ resolved calls, at ~400 bytes per `CallEdge` object: ~80 MB.

`pipeline_logger.call_resolutions` (capped at 10 000 entries, L320) is a bounded
diagnostic side-channel that persists across requests if the logger is process-global.

---

## 7. `RepositoryGraph`

**File**: `engine/repository/model/repository_graph.py`

`RepositoryGraph` is a **mutable** `@dataclass` (no `frozen=True`). Key fields:

```python
files: dict[str, FileContribution]  # per-file raw facts
symbols: dict[str, Symbol]  # all non-import symbols
imports: dict[str, Symbol]  # all import symbols
call_graph: CallGraph  # frozen: (edges tuple, _outgoing, _incoming)
reference_graph: ReferenceGraph
type_relationship_graph: TypeRelationshipGraph

# Reverse indexes — mutable, separate from graph data
symbol_to_callers: dict[str, set[str]]
symbol_to_importers: dict[str, set[str]]
unresolved_symbol_to_waiting_files: dict[str, set[str]]
file_to_call_edges: dict[str, list[Any]]
file_to_reference_edges: dict[str, list[Any]]
# ... 6 more file_to_* buckets
```

`rebuild_reverse_indexes()` (L119–197) scans every edge in all three graphs and every
construct, allocating new `set` and `list` containers for each key. For PostHog this
call touches ~400 000 edges.

**Edge indexing layers** (each layer references, not copies, the underlying objects):

| Layer | Where | Container type |
|---|---|---|
| Primary | `CallGraph.edges: tuple[CallEdge, ...]` | immutable tuple |
| Adjacency 1 | `CallGraph._outgoing: dict[str, tuple[CallEdge, ...]]` | dict of tuples |
| Adjacency 2 | `CallGraph._incoming: dict[str, tuple[CallEdge, ...]]` | dict of tuples |
| Reverse (graph) | `RepositoryGraph.symbol_to_callers: dict[str, set[str]]` | dict of sets |
| Per-file bucket | `RepositoryGraph.file_to_call_edges: dict[str, list]` | dict of lists |

`CallGraph.__post_init__` (L60–71 in `graphs.py`) builds `_outgoing` and `_incoming` via
intermediate mutable dicts, then converts each value from `list` to `tuple`. At peak
construction: `edges tuple + outgoing dict (lists) + incoming dict (lists) + _outgoing
dict (being built)`. Same pattern applies to `ReferenceGraph` and `TypeRelationshipGraph`.

`FileContribution` (one per source file) mirrors `FileIndex` with tuples of `SymbolEntry`,
`ImportEntry`, `CallEntry`, etc. These raw structural facts are kept alive in
`RepositoryGraph.files` indefinitely while the graph is cached.

---

## 8. `pipeline.py:513` — The pickle Clone

**File**: `engine/pipeline/pipeline.py`, **Line 513**

```python
# L510-514
# Clone base_graph using pickle to avoid mutating cache
pipeline_logger.log_pipeline(
    "[pipeline] Step 1.2: Cloning base RepositoryGraph...", to_terminal=True
)
clone_start = time.perf_counter()
patched_graph = pickle.loads(pickle.dumps(base_graph))
clone_duration = time.perf_counter() - clone_start
```

This is the **single largest memory event** in a normal PR analysis.

**`pickle.dumps(base_graph)`** recursively traverses the full `RepositoryGraph` object
graph and returns a `bytes` object proportional in size to the full serialized graph.

**`pickle.loads(...)`** deserializes a new, independent Python object graph. Every
`Symbol`, `CallEdge`, `ReferenceEdge`, `FileContribution`, `Evidence`, `FileLocation`,
`CallGraph`, `ReferenceGraph`, `TypeRelationshipGraph`, every `set` in the reverse
indexes — all become new Python objects.

**Memory footprint at the instant between `dumps` and `loads`:**

```
base_graph (live) + pickle bytes + patched_graph (being constructed)
≈ 3 × size_of_base_graph
```

In practice the peak is slightly under 3× because `loads` begins releasing the byte
stream incrementally, but CPython's allocator does not immediately return pages to the OS.

**Observed peak (from profiling):**

| Repository | Before clone | After clone | Delta |
|---|---|---|---|
| Polar | ~280 MB | ~560 MB | +280 MB |
| PostHog | ~940 MB | ~1 880 MB | +940 MB |

**Why this exists**: `base_graph` is held in `RepositoryStore` cache for reuse across
PRs. The pipeline must not mutate the cached graph, so it clones before patching.

---

## 9. `semantic_compiler.py` Hotspots

**File**: `engine/language/base/semantic_compiler.py`

### 9.1 Symbol Collection (Stage 1, L169–190)

`symbols: list[Symbol]` and `symbol_index: dict[str, Symbol]` grow in this stage. Each
`Symbol` allocation also creates an `Evidence` and `FileLocation`. For a 3 000-file repo
with 50 000 symbols: 20–40 MB.

### 9.2 Import Name Index (Stage 2, L198–201)

`name_to_symbols: dict[str, list[Symbol]]` is temporary but peaks during import
resolution before being released.

### 9.3 Call Graph Resolution (Stage 3, L227–362)

Five large lookup dicts coexist with the growing `call_edges: list[CallEdge]`. All five
are released after `_compile_impl` returns.

### 9.4 `frozenset(symbols)` at Line 520

```python
return RepositoryModel(symbols=frozenset(symbols), ...)
```

`frozenset()` hashes every `Symbol` and builds an internal hash table while the original
list is still live. For 50 000 symbols this is a brief but measurable peak.

`RepositoryModel.__post_init__` (L167–189 of `repository_model.py`) immediately builds
`_symbol_map: dict[str, Symbol]` — a second full indexing of every symbol.

### 9.5 `CallGraph.__post_init__` — Adjacency Index Construction (graphs.py L59–71)

```python
outgoing: dict[str, list[CallEdge]] = {}
incoming: dict[str, list[CallEdge]] = {}
for edge in self.edges:
    outgoing.setdefault(edge.caller_id, []).append(edge)
    incoming.setdefault(edge.callee_id, []).append(edge)
# Then: {k: tuple(v) for k, v in outgoing.items()}
```

At peak: `edges tuple + outgoing dict (lists) + incoming dict (lists) + _outgoing dict
(being built) + _incoming dict (being built)`. Same pattern for `ReferenceGraph` and
`TypeRelationshipGraph`.

---

## 10. `GraphPatcher`

**File**: `engine/language/base/graph_patcher.py`

`GraphPatcher.patch(base_graph, changed_files, language)` operates **in place** on the
cloned `patched_graph`:

1. Remove all edges, symbols, imports, and constructs for changed/deleted files.
2. Re-index the pruned graph.
3. Add new `FileContribution` objects for added/modified files.
4. Rebuild `CallGraph`, `ReferenceGraph`, `TypeRelationshipGraph` from scratch.
5. Call `patched_graph.rebuild_reverse_indexes()`.

Step 4 re-creates all frozen graph objects and their adjacency dicts. **This is the
second rebuild of adjacency indexes** (the first was in `rebuild_reverse_indexes` during
`compile_graph`). Old graph objects from the clone are released as each is reassigned.

Only changed files are re-indexed via `_index_single_file`. Unchanged files contribute
their existing `FileContribution` objects from the clone — shared references, no copy.

Memory during patching is transient: the old `CallGraph` (from clone) and new `CallGraph`
(being built) coexist briefly before the old is released.

---

## 11. `RepositoryGraph.clone()` vs `to_model()`

**`clone()` via pickle (L513)** — produces a full independent deep copy. Discussed in §8.

**`to_model()`** (`repository_graph.py:57–85`):

```python
def to_model(self) -> RepositoryModel:
    all_symbols = frozenset(self.symbols.values()) | frozenset(self.imports.values())
    model = RepositoryModel(
        symbols=all_symbols,
        call_graph=self.call_graph,          # shared reference — NOT copied
        reference_graph=self.reference_graph,
        type_relationship_graph=self.type_relationship_graph,
        entry_points=self.entry_points,
        ...
    )
```

**Critical observation**: `call_graph`, `reference_graph`, and `type_relationship_graph`
are passed by reference. After `to_model()`, `RepositoryModel` and `RepositoryGraph`
**share the same graph objects**. A mutation to the graph (e.g., by `GraphPatcher`)
after `to_model()` would be visible through `RepositoryModel`.

The only new allocations are:
- `frozenset(self.symbols.values()) | frozenset(self.imports.values())` — a new frozenset, but
  the `Symbol` objects inside are the same objects from the graph's dicts.
- `RepositoryModel.__post_init__` builds `_symbol_map: dict[str, Symbol]` — a new dict.

**`to_model()` memory cost ≈ frozenset header + `_symbol_map` dict**, approximately
10–15 MB for 50 000 symbols.

---

## 12. `RepositoryModel` — Immutable Snapshot

**File**: `engine/repository/model/repository_model.py`

`RepositoryModel` is `@dataclass(frozen=True)`. Fields:

- `symbols: frozenset[Symbol]`
- `call_graph: CallGraph` — shared with `RepositoryGraph` after `to_model()`
- `reference_graph: ReferenceGraph`
- `type_relationship_graph: TypeRelationshipGraph`
- `entry_points`, `async_entry_points`, `persistence_models`, `repository_methods`,
  `event_constructs`, `test_definitions`, `configuration_references`: tuples
- `metadata: dict[str, Any]`
- `_symbol_map: dict[str, Symbol]` — built in `__post_init__`, held for full lifetime

Two `RepositoryModel` instances exist simultaneously in `PipelineContext`:
`base_repository_model` and `head_repository_model`. For PostHog, each is ~400–500 MB;
both are alive until the `PipelineContext` is GC'd after the request returns.

---

## 13. Downstream Compilers

All models accumulate in `PipelineContext` and are held simultaneously:

| Field | Type | Constructed by | Approximate size |
|---|---|---|---|
| `change_model` | `ChangeModel` | `_compile_change()` | Small–medium: lists of changed symbols |
| `behavior_model` | `BehaviorModel` | `_compile_behavior()` | Execution chain trees; scales with entry point count |
| `ocm` | `OperationalChangeModel` | `_compile_operational()` | Derived from behavior model |
| `edm` | `EngineeringDiscoveryModel` | `_compile_discovery()` | Derived from OCM |
| `discovery_ir` | `DiscoveryIR` | `_compile_discovery_ir()` | Compact IR |
| `review_context` | `ReviewContext` | `_compile_review_context()` | Selects/normalizes facts from all above |
| `llm_context` | `LLMContext` | `_compile_llm_context()` | Compact token-efficient representation |

Downstream compilers operate on references to existing objects. They do not re-copy
`Symbol`, `CallEdge`, or graph structures.

---

## 14. LLM Context Construction

**File**: `engine/llm_context/compiler.py`

`LLMContextCompiler.compile(review_context)` builds a compact integer-indexed
representation in 9 phases:

1. **Noise pruning** — `build_review_scope` filters the `ReviewContext`.
2. **Changed symbol ID collection** — `set[str]` of symbol IDs.
3. **Entry point filtering and chain compression** — `_filter_entry_points`:
   retains origin, boundaries, changed steps, last step only.
4. **Symbol table** — `list[tuple[int, int, int]]` of `(file_id, name_idx, kind_id)`.
5. **File table** — `list[tuple[int, int]]`.
6. **Endpoint table** — `list[tuple[int, int]]`.
7. **Change files and summary** — compact integer-encoded change records.
8. **Execution DAG** — deduplicated graph of execution steps.
9. **Dead-string elimination** — compact `StringTable` (tuple of strings with
   remapped indices).

`_StringBuilder` accumulates all strings in a list with a deduplication index. The
final `LLMContext` holds tuples and small lists of integers.

**`LLMContext` is the smallest representation in the pipeline — measured in KB, not MB.**

---

## 15. Object Duplication Map

| Object | Original location | Duplicate(s) | Note |
|---|---|---|---|
| `RepositoryGraph` | `base_graph` in store | `patched_graph` (via pickle at L513) | **Full deep copy — only true duplication** |
| `CallEdge` objects | `call_graph.edges` tuple | `CallGraph._outgoing[*]`, `CallGraph._incoming[*]`, `file_to_call_edges[*]` | Same objects, 4 references; no copy |
| Symbol id strings | `Symbol.id` | Keys in `symbol_index`, `_symbol_map`, `symbol_to_callers`, `callee_name_to_ids` | Same str object; no copy (Python interns short strings) |
| `SymbolEntry` tuples | `FileIndex.symbols` | `FileContribution.symbols` via `from_file_index` | Same tuple objects; no copy |
| Decoded source `str` | `RepositorySnapshot.files` | `FileContext.source` | Same str reference; no copy |
| `Symbol` objects | `RepositoryGraph.symbols` / `imports` | `frozenset` in `RepositoryModel`, `_symbol_map` values | Same objects, 3 references |

---

## 16. Ownership and Lifetime Table

| Object | Owner | Created | Released |
|---|---|---|---|
| `zip_content: bytes` | local in `fetch_repository_at_sha` | After download completes | After ZipFile extraction loop returns |
| `files: dict[str, str]` | `RepositorySnapshot` | After extraction | After full request completes |
| `file_contexts: list[FileContext]` | local in `_build_index` | During AST parsing loop | After `compile_with_visitor` returns |
| AST nodes (`ast.*`) | `FileContext.ast` | During `ast.parse` | After `file_contexts` list is GC'd |
| `RepositoryIndex` | local in `compile_graph` | After indexing passes | After `compile_graph` returns |
| `base_graph: RepositoryGraph` | `FilesystemRepositoryStore` (on disk) | After `compile_graph` | Disk file persists; in-memory copy released after `compile_graph` |
| `patched_graph: RepositoryGraph` | local in `_compile_repository` | At L513 (pickle clone) | After `_compile_repository` finishes (held indirectly via head model) |
| `head_repository_model: RepositoryModel` | `PipelineContext` | After `to_model()` | After request handler returns |
| `base_repository_model: RepositoryModel` | `PipelineContext` | After base compile | After request handler returns |
| Intermediate compiler lists/dicts | local in `_compile_impl` | During semantic compilation | After `_compile_impl` returns |
| `PipelineContext` | `pipeline.run` → caller | Start of `pipeline.run` | After request handler returns |

---

## 17. Scaling Characteristics

Three metrics drive memory:

1. **File count (F)** — drives zip size, `FileContribution` count, AST count
2. **Symbol count (S)** — drives `Symbol` object count, id string count, `_symbol_map` size
3. **Call edge count (E)** — drives `call_edges` list, `CallGraph.edges` tuple, all
   adjacency index sizes

The pickle clone at L513 costs:

```
Δ_RSS ≈ sizeof(RepositoryGraph)
      + sizeof(all FileContributions)
      + sizeof(all Symbols + Evidence + FileLocation)
      + sizeof(CallGraph.edges + _outgoing + _incoming)
      + sizeof(ReferenceGraph edges + indexes)
      + sizeof(all reverse indexes)
      + sizeof(pickle bytes intermediate)
```

Empirically (PostHog: 8 k files, ~100 k symbols, ~400 k call edges):

| Component | RAM |
|---|---|
| `base_graph` in RAM | ~700–900 MB |
| pickle bytes | ~400–600 MB |
| `patched_graph` (new) | ~700–900 MB |
| **Peak simultaneous** | **~1 800–2 400 MB** |

Scaling is approximately **super-linear in E** because each `CallEdge` appears in four
containers (`edges tuple`, `_outgoing`, `_incoming`, `file_to_call_edges`) and creates
one `Evidence` + `FileLocation`.

---

## 18. Memory vs. Performance Trade-offs

| Decision | Memory cost | Performance benefit |
|---|---|---|
| `pickle.dumps/loads` clone (L513) | 2–3× peak spike | Correctness: cache isolation without field-by-field copying |
| `CallGraph._outgoing/incoming` dicts | ~2× edge data | O(1) caller/callee lookup |
| `RepositoryModel._symbol_map` | ~1× symbol id strings | O(1) `get_symbol_by_id` |
| `RepositoryGraph.symbol_to_callers` | ~1× callee id sets | O(1) reverse-dependency lookup in `GraphPatcher` |
| `RepositoryGraph.file_to_call_edges` | Negligible (list refs) | O(1) per-file edge extraction in `GraphPatcher` |
| `SymbolEntry` kept in `FileContribution` | ~1× raw index data | Allows re-indexing single files without re-parsing others |
| All `FileContext` live simultaneously | N × AST_size | Single AST traversal per file (composite visitor pattern) |
| `PipelineContext` holds all models | Sum of all models | No inter-compiler coordination needed |

---

## 19. Data Requirements

### Must remain in memory for full request lifetime

- `RepositorySnapshot.files` (base and head) — referenced by incremental compilation
- `base_repository_model` — used by change compiler
- `head_repository_model` — used by change, behavior, and downstream compilers
- `patched_graph` — held indirectly; shares `CallGraph` objects with `head_repository_model`
- All `PipelineContext` fields — downstream compilers pull from context

### Released after their producing stage exits

- `zip_content: bytes` — after extraction loop
- `file_contexts: list[FileContext]` — after `compile_with_visitor`
- `RepositoryIndex` — after `SemanticCompiler.compile` or `compile_graph` returns
- Intermediate lists/dicts in `_compile_impl` (`symbols`, `call_edges`, `reference_edges`,
  lookup dicts) — after `_compile_impl` returns

### Persisted across requests (disk cache, not RAM)

- `RepositoryGraph` serialized by `FilesystemRepositoryStore` as a `.pkl` file under
  `.cache/repositories/` (keyed by `SHA256("{repository}:{ref}")`).
- The graph is loaded fresh on each request via `pickle.load(f)` — it does not live in a
  process-level in-memory cache between requests (based on current `FilesystemRepositoryStore`
  implementation).

---

## 20. Top Memory Drivers Summary

Ranked by observed impact:

1. **pickle clone of `base_graph` (pipeline.py:513)** — single largest event; adds
   ~1× graph size to RSS. For PostHog: +940 MB.

2. **`CallGraph` + `ReferenceGraph` adjacency indexes (`_outgoing`, `_incoming`)**
   — built twice per request (once in `SemanticCompiler`, once after `GraphPatcher`).
   For PostHog: ~200 MB per graph pair × 2 rebuilds.

3. **`RepositoryGraph.rebuild_reverse_indexes()`** — third set of edge containers
   (`symbol_to_callers`, `file_to_call_edges`, etc.). For large repos: ~50–150 MB.

4. **`RepositoryModel._symbol_map` dict** — built in `__post_init__`, held for full
   request lifetime. For 100 k symbols: ~30–60 MB.

5. **`FileContribution` tuple fields in `RepositoryGraph.files`** — raw structural
   facts for every file. For PostHog: ~150–250 MB.

6. **Source text `dict[str, str]`** — approximately 1× compressed repo size after
   decoding. For PostHog: ~200–400 MB (held for full request).

7. **`CallEdge` and `ReferenceEdge` lists** during `_compile_impl` — transient but
   large during semantic compilation. For PostHog: ~80–200 MB.

8. **Both `base_repository_model` and `head_repository_model` alive simultaneously**
   — for PostHog each is ~400–500 MB; together they sustain ~1 GB during downstream
   compilation.

---

## 21. Open Questions

1. **Is `base_graph` deserialized fresh per request or held in process memory?**
   `FilesystemRepositoryStore.load` calls `pickle.load(f)` on every cache hit — a fresh
   object is deserialized each time. A process-level `MemoryRepositoryStore` would avoid
   repeated deserialization but pin the graph in RAM between requests.

2. **Why is a full pickle clone required rather than a partial structural copy?**
   The graph's mutable fields (`symbol_to_callers: dict[str, set[str]]`,
   `file_to_call_edges: dict[str, list]`, etc.) are modified in place by `GraphPatcher`.
   A deep copy is required to avoid corrupting the cached base. Whether those mutable
   reverse indexes need to be included in the clone at all — or could be rebuilt cheaply
   after patching — is an open design question.

3. **When must both `base_repository_snapshot` and `head_repository_snapshot` coexist?**
   If the head snapshot can be discarded after incremental compilation, source-text memory
   could be halved for large repositories.

4. **Can `RepositoryIndex` be freed earlier?** After `compile_graph`, the
   `RepositoryIndex` is no longer referenced at the Python level, but `FileContribution`
   (a structural mirror of `FileIndex`) is kept alive in `RepositoryGraph.files`. If
   `FileContribution` were stored in a more compact form (e.g., pre-serialized bytes),
   the in-process footprint of the cached graph would shrink.

5. **Is `RepositoryModel._symbol_map` necessary for all downstream compilers, or only
   a subset?** If only the behavior compiler uses `get_symbol_by_id`, the dict could be
   built lazily or passed explicitly rather than allocated in `__post_init__`.
