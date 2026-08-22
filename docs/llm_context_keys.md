# LLM Context Keys

This document defines every field in the `LLMContext` — the compressed, token-efficient intermediate representation (IR) produced by the `LLMContextCompiler` and fed directly into the LLM prompt.

**System background**: Factor analyses a code change (PR / diff) by building a `ReviewContext` with three sections — `change`, `execution`, and `discoveries`. The `LLMContextCompiler` then compresses `ReviewContext` into `LLMContext` using a set of compression rules: enum-encoding repeated categorical values, a global string table to de-duplicate strings, compact positional tuples instead of verbose objects, and a DAG to collapse duplicate execution chains. All fields use 1–3 character names to minimise tokens.

---

## st — String Table

**Type**: `StringTable(entries: tuple[str, ...])`

A global dictionary storing every distinct string used anywhere in the context — file paths, symbol names, endpoint paths, service names, module names. All other fields reference strings by their integer index into this table. Index `0` is always reserved for the empty string.

**How it is built**: The compiler collects strings while building all other sections, then performs *dead-string elimination* — any string that ends up unreferenced by an emitted object is removed and indices are remapped before the final output is produced.

**Why it matters**: De-duplicating strings is the single biggest source of token reduction. A file path that appears in dozens of execution steps is stored once; every step carries only a small integer reference.

---

## f — Files

**Type**: `tuple[tuple[int, int], ...]`
**Shape per entry**: `(path_idx, ct_id)`

- `path_idx` — index into `st` for the file path.
- `ct_id` — integer from `ENUM_CT` encoding the change type (`modified`, `added`, `removed`, `renamed`, `copied`, `mixed`).

**How it is built**: Takes all files from `ChangeContext.files`, filters to only *retained* files — changed files plus files that contain any chain-referenced symbol — and emits one entry per unique file path.

**Why it matters**: Gives the LLM the exact set of files touched by the change and the nature of each change, without repeating the path string everywhere.

---

## sym — Symbols

**Type**: `tuple[tuple[int, int, int], ...]`
**Shape per entry**: `(file_id, name_idx, kind_id)`

- `file_id` — index into `f` (which file this symbol lives in).
- `name_idx` — index into `st` for the symbol name. Set to `0` (empty) when the name is fully derivable from the symbol's `sym://` URI to avoid redundancy.
- `kind_id` — integer from `ENUM_KIND` encoding the symbol kind (`function`, `method`, `class`, `endpoint`, `worker`, `task`, `route`, `property`, `attribute`, `parameter`, `module`, `package`, `interface`, `enum`, `constant`, `type_alias`, `decorator`, `exception`).

**How it is built** — three-pass, discovery-centred:
1. **Pass 1 (always)**: All changed symbols from `ChangeContext.files`.
2. **Pass 2 (budget-gated)**: Symbols referenced by retained execution chains, subject to a per-file cap (`LLM_CONTEXT_MAX_SYMBOLS_PER_FILE`).
3. **Pass 3**: Symbols directly referenced by discoveries (via `sym://` URIs) from any retained chain, even if that chain's entry point was budget-pruned.

**Why it matters**: The canonical symbol registry for the entire context. Every execution graph node and every `cf` entry references symbols by index into this table — no name/kind/location is ever repeated.

---

## ep — Endpoints

**Type**: `tuple[tuple[int, int], ...]`
**Shape per entry**: `(method_id, path_idx)`

- `method_id` — integer from `ENUM_METHOD` encoding the HTTP verb or trigger type (`POST`, `GET`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`, `worker`, `event`, `cron`, `webhook`).
- `path_idx` — index into `st` for the endpoint route or trigger identifier.

**How it is built**: The compiler collects entry points from `ExecutionContext.entry_points`, enforces an endpoint budget (`LLM_CONTEXT_MAX_ENDPOINTS`), and prioritises entry points whose execution chains touch changed files. Endpoints touching changed files are always preferred; remaining slots are filled deterministically.

**Why it matters**: The index of all API surfaces or trigger surfaces affected by the change. The execution section (`epts`) references entries in this table by index.

---

## cs — Change Summary

**Type**: `tuple[int, int, int, int, int]`
**Shape**: `(cls_id, scope_id, file_count, sym_count, bh_count)`

- `cls_id` — integer from `ENUM_CLS` classifying the overall change (`modification`, `addition`, `removal`, `refactor`, `fix`, `feature`, `mixed`).
- `scope_id` — integer from `ENUM_SCOPE` describing the blast radius (`local`, `multi_file`, `cross_package`, `cross_service`, `global`).
- `file_count` — total number of files changed.
- `sym_count` — total number of symbols changed.
- `bh_count` — total number of behavioural findings (discoveries).

**How it is built**: Directly from `ChangeSummary` on `ChangeContext` — no recomputation.

**Why it matters**: A single 5-integer tuple gives the LLM a high-level snapshot of the change's size and scope before it reads the details. The LLM uses this to calibrate reasoning depth.

---

## cf — File Changes

**Type**: `tuple[tuple[int, tuple[int, ...]], ...]`
**Shape per entry**: `(file_idx, (sym_idx_1, sym_idx_2, ...))`

- `file_idx` — index into `f` (which file changed).
- Inner tuple — indices into `sym` for every symbol that was changed inside that file.

**How it is built**: For each retained file in `ChangeContext.files`, the compiler walks every symbol change and maps it to that symbol's index in `sym`. Only symbols already registered in `sym` are emitted here.

**Why it matters**: The precise change surface — the LLM knows exactly which symbols inside each file were modified. Combined with `sym`, this answers "which functions/classes changed in which files?"

---

## eg — Execution Graph

**Type**: `ExecutionGraph(nodes, edges)`

### nodes — `tuple[tuple[int, int, int, int], ...]`
Shape per node: `(sym_idx, depth, reaches_svc_idx, reaches_mod_idx)`

- `sym_idx` — index into `sym` for the symbol executing at this step.
- `depth` — execution depth from the originating entry point (`0` = the entry point handler itself).
- `reaches_svc_idx` — index into `st` for the external service this step reaches (e.g., `"stripe"`, `"redis"`, `"sendgrid"`). `0` if none.
- `reaches_mod_idx` — index into `st` for the module or package this step reaches. `0` if none.

### edges — `tuple[tuple[int, int], ...]`
Shape per edge: `(parent_node_idx, child_node_idx)`

A directed edge from parent node to child node, representing the execution call flow.

**How it is built**: The compiler flattens all retained, compressed execution chains into a single DAG. Nodes with the same `(behavior, symbol.id)` key are deduplicated — shared call-path prefixes across multiple entry points collapse into one node, and edges are shared too. Each chain is first *compressed* to evidence-bearing steps only:

- First step (origin — the entry point handler).
- Any step whose symbol is in the changed-symbol set.
- Any step where `reaches.service != ""` — a **boundary crossing**, where execution leaves the current service.
- Last step (terminal — the external effect: DB write, queue publish, HTTP call, etc.).

Intermediate helper-only steps are collapsed away.

**Why it matters**: The primary reasoning surface for the LLM. It shows *how* a code change propagates at runtime — which functions call which, how deep the call stack goes, and whether execution crosses a service boundary (e.g., calls Stripe, enqueues a Celery task, writes to Redis).

---

## epts — Entry Points

**Type**: `tuple[tuple[int, tuple[int, ...], int, int], ...]`
**Shape per entry**: `(ep_idx, (node_idx_1, node_idx_2, ...), terminal_idx, max_depth)`

- `ep_idx` — index into `ep` (which endpoint/trigger is the entry point).
- Inner tuple — ordered sequence of node indices in `eg.nodes` forming this entry point's compressed execution walk through the shared DAG.
- `terminal_idx` — index into `st` for the terminal point kind (e.g., `"database"`, `"external_api"`, `"queue"`). `0` if none.
- `max_depth` — the deepest execution depth reached from this entry point.

**How it is built**: One entry per retained entry point. The node sequence is derived from the compressed chain's traversal of the shared execution DAG.

**Why it matters**: Bridges `ep` (which API surface) to `eg` (what happens at runtime). The LLM uses `epts` to answer "which API handler triggers which call path, does it cross a service boundary, and how deep does it go?"

---

## disc — Discoveries

**Type**: `tuple[tuple[int, dict[str, Any]], ...]`
**Shape per entry**: `(kind_id, facts)`

- `kind_id` — integer from `ENUM_BH_KIND` classifying the discovery:

| ID | Kind | Meaning |
|---|---|---|
| 1 | `deep_execution` | A call chain reaches unusual depth from an entry point. |
| 2 | `shared_execution` | A symbol is shared across multiple entry points — fan-out risk. |
| 3 | `boundary_crossing` | Execution crosses a service boundary (e.g., HTTP call, queue publish). |
| 4 | `event_publication` | The change emits or modifies a published event. |
| 5 | `hidden_relationship` | A non-obvious dependency between two otherwise-unrelated symbols. |
| 6 | `public_interface_change` | A public API surface (endpoint signature, event schema) is altered. |
| 7 | `shared_dependency` | A dependency shared with other services is modified. |
| 8 | `state_mutation` | A shared state store (DB, cache) is written by the change path. |
| 9 | `validation_gap` | A code path lacks adequate validation after the change. |
| 10 | `entry_point` | Structural: this node is an execution entry point. |
| 11 | `terminal_point` | Structural: this node is an execution terminal (final effect). |
| 12 | `reachable_unit` | Structural: this node is reachable from a changed entry point. |
| 13 | `execution_chain` | Structural: a complete call chain from origin to terminal. |

- `facts` — structured dictionary of deterministic data for the discovery (includes `hook`, `finding`, `evidence`, and any discovery-specific structured fields).

**How it is built**: `LLMContextCompiler._build_discoveries()` iterates `ReviewContext.discoveries` and enum-encodes each one. Discoveries are the **anchors** of the entire LLM context build — the compiler operates discovery-centred, meaning every other emitted object (symbol, file, execution chain) must be reachable from at least one discovery or originate from a changed symbol.

**Why it matters**: Discoveries are the highest-signal output of the system — deterministic engineering conclusions that a human reviewer would care about, e.g., "this change now reaches the Stripe webhook handler" or "this method is called from 7 different entry points". The LLM uses `disc` as the primary input for generating the review narrative.

---

## Enum Tables Reference

All integer IDs resolve to strings via lookup tables in [`engine/llm_context/model.py`](file:///Users/jishnupsamal/Jishnu/Factor/cystatic-core/engine/llm_context/model.py):

| Enum | Used in | Key values |
|---|---|---|
| `ENUM_KIND` | `sym[*][2]` | `class`, `function`, `method`, `endpoint`, `worker`, `task`, `route`, `property`, `attribute`, `parameter`, `module`, `package`, `interface`, `enum`, `constant`, `type_alias`, `decorator`, `exception` |
| `ENUM_CT` | `f[*][1]` | `modified`, `added`, `removed`, `mixed`, `renamed`, `copied` |
| `ENUM_METHOD` | `ep[*][0]` | `POST`, `GET`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`, `worker`, `event`, `cron`, `webhook` |
| `ENUM_CLS` | `cs[0]` | `modification`, `addition`, `removal`, `refactor`, `fix`, `feature`, `mixed` |
| `ENUM_SCOPE` | `cs[1]` | `local`, `multi_file`, `cross_package`, `cross_service`, `global` |
| `ENUM_BH_KIND` | `disc[*][0]` | See table in `disc` section above |
| `ENUM_BH_CHANGE` | (reserved) | `FunctionBodyChange`, `SignatureChange`, `ClassBodyChange`, `InterfaceChange`, `ImportChange`, `DecoratorChange`, `TypeAnnotationChange`, `DocstringChange`, `VisibilityChange`, `AsyncChange`, `ExceptionChange`, `DependencyChange`, `ConfigurationChange`, `RouteChange`, `SchemaChange`, `MigrationChange`, `TestChange`, `ReturnTypeChange`, `ParameterChange`, `AccessModifierChange` |

Index `0` in every enum table is always the empty/unknown value.

---

## Structure Summary

```
LLMContext
├── st    — string table (all strings, de-duplicated; referenced by index everywhere)
├── f     — files changed (path_idx + change_type)
├── sym   — symbol registry (file_id + name_idx + kind_id)
├── ep    — endpoints / triggers affected (method_id + path_idx)
├── cs    — change summary (cls + scope + counts)
├── cf    — per-file symbol changes (file_idx → [sym_idx, ...])
├── eg    — execution DAG (nodes: sym+depth+reaches; edges: parent→child)
├── epts  — entry point traversals (ep_idx → chain walk → terminal + max_depth)
└── disc  — discoveries (kind_id + structured facts dict)
```

*Document last updated: 2026-08-18.*