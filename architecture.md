# Factor — System Architecture

## What Factor Does

Factor is a **blast-radius and refactor-risk analysis engine** for code changes. Given a PR (or raw diff), it determines which downstream services, endpoints, databases, and queues are impacted, assigns a confidence-weighted verdict, and posts a structured PR comment — all without requiring the reviewer to hold the full system in their head.

The core design principle: **causal-graph propagation drives the verdict; the LLM is a contextual override; failure templates are optional hypotheses that never drive upgrades.**

---

## High-Level Flow

```
PR webhook / API request
  │
  ▼
Source Adapter Layer         fetch diff + file snapshots
  │                           (GitHub / GitLab)
  ▼
Language Adapter Layer       per-language static analysis
  │                           (Python / TypeScript)
  ▼
Canonical IR + Compressor    normalize → compress for LLM budget
  │
  ▼
Core Engine Pipeline
  ├── Risk Pattern Detector         detect risky code shapes
  ├── Entry Point Resolver          affected HTTP/event/CLI entry points
  ├── Behavior Extractor            before/after behavior per symbol
  ├── Behavior Diff Builder         symbol-level behavioral diffs
  ├── Reachability Classifier       can each change be reached?
  ├── Side Effect Detector          mutation / IO / state side effects
  ├── Causal Graph Builder          symbol→symbol edges with confidence
  ├── Repo-Wide Symbol Index        expand known symbols past diff boundary
  ├── Propagation Engine            impact tree (≤5 hops, confidence-weighted)
  ├── Failure Templates             optional hypothesis matching (lazy)
  ├── System Behavior Deltas        system-level behavioral change summary
  ├── Structured Hypotheses         testable claims on causal edges
  └── Scenario Validator            score LLM failure scenarios
  │
  ▼
LLM Failure Simulation       (optional — OpenAI, with fallback to rules)
  │
  ▼
Verdict Aggregation          blast radius primary, LLM secondary
  │
  ▼
PR Comment (Jinja2)          + persisted run (Tortoise ORM → Postgres)
```

---

## Directory Layout

```
cystatic-core/
├── api/                        FastAPI service
│   ├── main.py                 app entrypoint (uvicorn api.main:app)
│   ├── models.py               Tortoise ORM models + persist_analysis_result
│   ├── db.py                   Tortoise config (runtime)
│   ├── db_migrations.py        Aerich migration config
│   ├── settings.py             pydantic-settings configuration
│   ├── utils.py                shared helpers
│   ├── admin/urls.py           admin API routes
│   └── user/urls.py            user-facing API routes
│
├── core_engine/                analysis brain
│   ├── orchestrator.py         BaseOrchestrator + Orchestrator + DiffOrchestrator
│   ├── causal_graph.py         CausalGraph, CausalEdge, EvidenceNode, WeakEdge,
│   │                           RepositorySymbolIndex, build_causal_graph
│   ├── propagation_engine.py   ImpactTree, ImpactNode, PropagationEngine
│   ├── risk_pattern_detector.py RiskPatternDetector, detect_flows
│   ├── risk_flags.py           RiskEventType enum
│   ├── entrypoint_resolver.py  EntryPointResolver, EntryPoint, SystemImpact
│   ├── behavior_extractor.py   extract_behavior_deltas
│   ├── behavior_diff_builder.py build_behavior_diffs
│   ├── behavior_delta_system.py build_system_behavior_deltas, SystemBehaviorDelta
│   ├── reachability_classifier.py ReachabilityClassifier
│   ├── side_effect_detector.py SideEffectDetector
│   ├── rir_compressor.py       RIRCompressor (legacy + v3)
│   ├── factor_ir_v3.py         IR schema definitions
│   ├── failure_templates.py    match_failure_templates (optional, lazy)
│   ├── failure_simulation_llm.py LLM-based failure simulation
│   ├── failure_simulator.py    rules-based fallback simulator
│   ├── scenario_validator.py   score_scenarios, ValidationScore
│   └── file_exclusion.py       FileExclusionService
│
├── language_adapters/          per-language static analysis
│   ├── python/python_adapter.py  Python adapter (DIFF_ONLY + FULL_FILE)
│   ├── ts_adapter.py            TypeScript adapter
│   └── interfaces/              adapter protocol definitions (WIP)
│
├── source_adapters/            source-control integration
│   ├── github_adapter.py       legacy GitHub adapter
│   ├── gitlab_adapter.py       GitLab adapter
│   └── github/                 full GitHub integration
│       ├── github_client.py    fetch diffs, file snapshots, SHAs
│       ├── auth.py             installation auth, JWT, token exchange
│       ├── bot.py              post comments to PRs
│       ├── event_handler.py    dispatch webhook events to jobs
│       ├── comment_formatter.py render PR comments
│       └── webhook.py          webhook parsing + signature validation
│
├── github_app/                 GitHub App layer (alternative entrypoint)
│   ├── webhook.py
│   ├── auth.py
│   ├── github_client.py
│   ├── event_handler.py
│   └── comment_formatter.py
│
├── schemas/                    Pydantic models
│   ├── api.py                  AnalyzeRequest, etc.
│   ├── ir.py                   IR data structures
│   └── failure_simulation.py   FailureSimulation output schema
│
├── workers/                    async job processing
│   ├── queue.py                Dramatiq Redis broker
│   └── analyze_pr.py           worker entrypoint
│
├── instrumentation/            observability
│   └── sentry/                 Sentry middleware + request context
│
├── templates/
│   └── github/pr_comment.md.j2 PR comment Jinja2 template
│
├── tests/                      pytest suite
│   ├── core_engine_tests.py    causal graph + propagation
│   ├── test_evidence_graph.py  evidence graph construction
│   ├── test_weak_edges.py      weak edge detection
│   ├── test_shared_state_resource_model.py  shared-state coupling
│   ├── test_repo_symbol_index.py  repo-wide symbol index
│   ├── github_webhook_tests.py webhook parsing + dispatch
│   ├── github_worker_tests.py  worker + orchestrator integration
│   ├── language_adapter_tests.py
│   ├── source_adapter_tests.py
│   └── test_webhook.py
│
└── utils/
    └── unzip.py                archive extraction
```

---

## Core Engine — In Detail

### Orchestrator (`orchestrator.py`)

The orchestrator is the pipeline spine. Two concrete strategies share the same `BaseOrchestrator` backbone:

| Strategy | Mode | Repo Access | When to Use |
|---|---|---|---|
| `Orchestrator` | `FULL_FILE` | Fetches diff + full file snapshots at head SHA | Production (GitHub App, API) |
| `DiffOrchestrator` | `DIFF_ONLY` | Raw diff text only, no repo snapshots | Demo / sandbox / CI without repo token |

Both run the same shared pipeline (`_run_causal_pipeline`) and the same verdict aggregation logic.

**`Orchestrator.run_pr_analysis()` step by step:**

1. Fetch the PR diff via the source adapter.
2. Apply file exclusions (`FileExclusionService`).
3. Fetch full file snapshots at head SHA for each changed file.
4. Run language adapter in `FULL_FILE` mode: extract changed functions, endpoints, keyword signals.
5. Collect `(file_path, content)` pairs for repo-wide symbol indexing (zero extra HTTP calls — reuses already-fetched snapshots).
6. Enrich each file (risk score, flows, endpoint mapping).
7. Build `RepositorySymbolIndex` from collected snapshots (expands `known_symbols` past the diff boundary).
8. Detect risk patterns, resolve entry points, extract behavior deltas and diffs.
9. Classify reachability, detect side effects.
10. Compress IR (legacy + v3) for LLM budget.
11. Run the **causal pipeline**: causal graph → impact tree → failure templates → system deltas → structured hypotheses.
12. Call LLM with causal context (or fall back to rules-based simulator).
13. Score scenarios via `scenario_validator`.
14. Aggregate verdict (blast radius primary, LLM secondary).
15. Build and return the result dict.
16. (Async) Persist via `persist_analysis_result`.

`DiffOrchestrator` follows the same steps but skips snapshot fetching and repo-index construction (steps 3, 5, 7). The pipeline degrades gracefully — propagation stays diff-bound.

---

### Causal Graph (`causal_graph.py`)

The causal graph is the **non-negotiable core primitive**. It turns "diff understanding" into "system simulation" by modeling symbol-to-symbol relationships with typed, confidence-weighted edges.

**Node types** (`CausalNode.node_type`):

| Type | Represents |
|---|---|
| `symbol` | A function/method in the diff or repo |
| `endpoint` | An HTTP route, CLI entry point, or event handler |
| `service` | An external service boundary |
| `database` | A datastore (Postgres, Redis, etc.) |
| `queue` | A message queue / event bus |
| `shared_state` | A named resource (e.g. `cache:user`, `redis:cart`, `session:token`) |

**Edge types** (`CausalEdge.edge_type`):

| Type | Meaning |
|---|---|
| `data_flow` | Result flows from one symbol to another |
| `control_flow` | One symbol gates execution of another |
| `shared_state` | Shared state coupling (cache/redis/session) |
| `async_event` | Event emitted between symbols |
| `db_dependency` | Database read/write dependency |
| `transaction_boundary` | Shared transaction boundary |

Each `CausalEdge` carries **evidence grounding**: `evidence_type` (function_call, assignment, return, shared_access, db_operation, async_emit, transaction_boundary, import_reference), `evidence_location` (file:line), and `evidence_snippet` (the actual code line).

**Weak edges** (`WeakEdge`) are a Phase 2 concept — evidence edges with a different type taxonomy (CALLS, SHARES_STATE, DATA_FLOW, CONTROL_FLOW, CONTRACT_DEPENDENCY). Every `WeakEdge` must have ≥1 evidence string. These feed into the evidence graph layer.

**Evidence nodes** (`EvidenceNode`) carry `SymbolSignals` — lightweight behavioral signals extracted via static heuristics: `is_entrypoint`, `is_io`, `writes_state`, `reads_state`, `calls`, `called_by`, `imports`. This is the "evidence token" layer that makes the causal graph actionable.

**`build_causal_graph()`** constructs the full graph from enriched files, behavior diffs, and an optional `RepositorySymbolIndex`. The repo index expands `known_symbols` to include every defined function in the repo and registers all endpoints — not just the ones in the diff. This unlocks richer blast-radius propagation that reaches past the diff boundary.

---

### Repository-Wide Symbol Index

Pre-scans the entire repository (when available) and indexes:
- All function/method definitions (the set of "known" symbols)
- All route definitions (endpoints) across all files
- Which file each symbol lives in

This is built from the snapshots already fetched for the diff — zero extra HTTP calls. When `None` (DIFF_ONLY mode), the pipeline falls back to diff-only behavior.

---

### Propagation Engine (`propagation_engine.py`)

Given a causal graph and a set of changed symbols, computes: *"if X changes → what downstream nodes are impacted and with what confidence?"*

**Strategy:**
1. Start from directly changed symbols (roots).
2. Traverse downstream through the causal graph.
3. Propagate confidence: `confidence_child = confidence_parent × edge.confidence`.
4. Aggregate repeated paths by taking max confidence.
5. Cap at `max_hops=5` (configurable).

**Output:** `ImpactTree` containing:
- `roots`: directly changed `ImpactNode`s
- `all_nodes`: every reachable `ImpactNode` keyed by symbol
- `get_blast_radius()`: summary with impacted services, endpoints, databases, queues, shared-state resources, downstream symbols, critical paths, max/avg confidence.

Each `ImpactNode` carries: `symbol`, `confidence`, `hop_distance`, `incoming_edges` (list of `CausalEdge`), `is_direct_change`, `impacted_systems`, `node_type`, `evidence_location`, `evidence_snippet`.

---

### Risk Detection

**`RiskPatternDetector`** scans enriched files for risky code shapes — authentication changes, payment logic, transaction boundaries, validation removal, financial data model changes, schema migrations, etc. Each risk has a `RiskEventType` (from `risk_flags.py`), a confidence, file path, trigger, and reason.

**`detect_flows()`** annotates each enriched file with data-flow patterns (e.g. auth-gated flows, payment flows).

**`EntryPointResolver`** identifies which HTTP/event/CLI entry points are affected by the detected risk patterns, and resolves system-level impact (`SystemImpact` — which services/areas are at risk).

---

### Behavior Analysis

| Module | Purpose |
|---|---|
| `behavior_extractor.py` → `extract_behavior_deltas()` | Produces per-symbol before/after behavioral descriptions (what the function *does*, not just what changed) |
| `behavior_diff_builder.py` → `build_behavior_diffs()` | Produces structured `BehaviorDiff(symbol, before, after)` for each changed function |
| `behavior_delta_system.py` → `build_system_behavior_deltas()` | Aggregates symbol-level deltas into system-level behavioral change summaries (`SystemBehaviorDelta`) |

These feed into the causal graph, the LLM prompt, and the structured hypotheses.

---

### Supporting Analysis Modules

| Module | Purpose |
|---|---|
| `ReachabilityClassifier` | Classifies whether each changed symbol is reachable from production entry points |
| `SideEffectDetector` | Detects mutation, IO, and state side effects in changed code |
| `RIRCompressor` | Compresses enriched files into a token-budgeted IR for the LLM (legacy `compress` + v3 `compress_v3`) |
| `factor_ir_v3.py` | IR schema definitions for the canonical representation |
| `FileExclusionService` | Excludes lockfiles, generated code, assets, etc. from analysis |

---

### Failure Templates (`failure_templates.py`)

An **optional hypothesis layer** — lazy-imported, gracefully degrading. Matches known failure patterns (e.g. "auth bypass", "silent data loss", "missing rollback") against risk patterns, enriched files, and behavior diffs. Returns a list of matched template dicts.

**Critical design rule:** failure templates are treated as optional hypotheses, not core signals. They do NOT drive verdict upgrades. Only blast-radius propagation does.

---

### LLM Failure Simulation

**`FailureSimulationLLM`** (`failure_simulation_llm.py`) calls OpenAI with:
- Compressed IR
- Causal graph (serialized)
- Impact tree blast radius
- Failure template matches
- System behavior deltas

Returns a structured `FailureSimulation` (Pydantic model) with failure scenarios, hidden impact chains, verdict, verdict rationale, etc.

**`FailureSimulator`** (`failure_simulator.py`) is the rules-based fallback when the LLM is unavailable or fails. Generates failure scenario lines from risk patterns and enriched files.

Both outputs are normalized and sanitized (`_sanitize_llm_output`, `_normalize_failure_simulation`) — defensive parsing of LLM output per the project's LLM-handling rule.

---

### Scenario Validation (`scenario_validator.py`)

`score_scenarios()` evaluates each LLM-generated failure scenario against the compressed IR. Produces `ValidationScore` containing:
- Per-scenario `ScenarioScore` with `confidence_adjustment` multiplier and `issues` list
- Top-level `warnings` and `notes`

Validation is **soft scoring, not hard rejection** — confidence is adjusted downward for unsupported scenarios, but nothing is discarded outright.

---

### Structured Hypotheses

`_build_structured_hypotheses()` (on the orchestrator) attaches testable claims to specific causal edges in the graph. For each impacted symbol with an incoming causal edge, it generates a hypothesis template based on edge type (e.g. "If {from} changes, {to} may receive unexpected input through data flow"). Hypotheses are cross-referenced with failure template matches for confidence boosting. Capped at 20, sorted by confidence.

---

### Verdict Aggregation

`BaseOrchestrator._aggregate_verdict()` makes the final call:

1. **If blast radius exists** (impacted services/endpoints/databases): base verdict = `LOW_RISK`, promoted to `UNCERTAIN_IMPACT` (confidence ≥ 0.25) or `REVIEW_REQUIRED` (≥ 0.6).
2. **LLM override** (only strong verdicts `SAFE` or `BLOCK_REVIEW`): the LLM sees code context the graph can't — it may override the blast-radius verdict.
3. **No propagation + silent LLM**: `NO_SIGNIFICANT_PROPAGATION_FOUND`.

**Allowed final verdict set:**
`SAFE` · `LOW_RISK` · `UNCERTAIN_IMPACT` · `NO_SIGNIFICANT_PROPAGATION_FOUND` · `REVIEW_REQUIRED` · `BLOCK_REVIEW`

---

## Source & Language Adapters

### Source Adapters

| Adapter | Status | Capabilities |
|---|---|---|
| `source_adapters/github/` | Production | Full integration: `GitHubClient` (fetch diff, file snapshots, SHAs), `GitHubBot` (post comments), auth (installation JWT, token exchange), webhook parsing + signature validation, event handler (dispatch to jobs) |
| `github_app/` | Alternative entrypoint | Same capabilities, separate package for GitHub App lifecycle |
| `github_adapter.py` | Legacy | Simpler interface, used by `DiffOrchestrator` |
| `gitlab_adapter.py` | Stub | `fetch_not_implemented` — placeholder for future work |

### Language Adapters

| Adapter | Capabilities |
|---|---|
| `python/python_adapter.py` | `extract_changed_files`, `extract_changed_functions` (FULL_FILE + DIFF_ONLY modes), `extract_endpoints` (FastAPI, Flask, Django), `extract_keyword_signals_from_diff`. Uses AST analysis for function extraction. |
| `ts_adapter.py` | TypeScript equivalent (regex/heuristic-based) |

Both adapters produce `enriched_files` dicts consumed by the core engine.

---

## Data Model (Tortoise ORM → Postgres)

11 runtime tables + 1 eval-harness table:

| Table | Purpose |
|---|---|
| `organizations` | Tenant (installation id, org login, plan, billing, onboarding) |
| `repositories` | Repo metadata, language breakdown, framework hints, last-analysis pointers |
| `pull_requests` | PR header (SHAs, state, changed files, factor verdict) |
| `analysis_runs` | One row per (PR, head_sha, triggered_by). Status, verdict, risk score, **`analysis_snapshot`** (entire result JSON), `internal_reasoning_artifacts` |
| `pull_request_snapshots` | Per-run input snapshot with `raw_payload` = full result JSON |
| `analysis_artifacts` | Generic artifact storage (compressed IR, etc.) |
| `deterministic_analyzer_outputs` | Structured deterministic pass: files, risk patterns, entry points, dependency graph, denormalised lists (impacted services, execution paths, auth boundary changes, etc.) and counts |
| `risk_findings` | One row per risk pattern (category, severity, confidence, evidence, code locations) |
| `analysis_comments` | Canonical PR comment body (full markdown, linked to run) |
| `analysis_jobs` | Queue state (status, attempts, lease, idempotency key, delivery id for dedup) |
| `feedback_signals` | Explicit user feedback / thumbs |
| `evaluation_cases` | Eval harness cases (expected verdict, expected findings, historical misses) |

**Persistence flow:** `Orchestrator.log_run()` → `persist_analysis_result()` writes all 11 tables in a single call. The entire orchestrator result dict is also dumped into `AnalysisRun.analysis_snapshot` as JSON — nothing is lost.

---

## Workers & Queue

- **Broker:** Dramatiq on Redis (`workers/queue.py`). URL resolution: `REDIS_URL` → derived `rediss://` from `UPSTASH_REDIS_REST_*` → `localhost`.
- **Worker:** `workers/analyze_pr.py` — receives a job, runs `Orchestrator.run_pr_analysis()`, posts the comment, persists the result.
- **Dedup:** `delivery_id` on both `AnalysisRun` and `AnalysisJob` prevents double-runs on webhook retries. `AnalysisJob.idempotency_key` is unique.

---

## API

- **Framework:** FastAPI + Uvicorn/Gunicorn
- **ORM:** Tortoise ORM on asyncpg (Neon Postgres)
- **Routers:** `api/admin/urls.py` (admin routes) + `api/user/urls.py` (user routes)
- **Settings:** pydantic-settings (`api/settings.py`)
- **DB config:** `api/db.py` (runtime, pooled Neon URL) + `api/db_migrations.py` (Aerich, direct Neon URL)
- **Schema generation:** disabled at runtime (`generate_schemas=False`)

---

## Observability

- **Sentry** middleware attached to the FastAPI app (`instrumentation/sentry/sentry.py`).
- Per-request context helpers (`instrumentation/sentry/contexts.py`) attach repo, PR number, analysis run ID, etc. to Sentry events.

---

## PR Comment

Rendered by `_render_pr_comment()` against `templates/github/pr_comment.md.j2` (Jinja2). Variables include `verdict`, `failure_simulation` (normalized), and the full analysis result. The rendered body is stored in `analysis_comments.body` and linked back to the run via `AnalysisRun.canonical_comment`.

---

## Key Design Decisions

1. **Blast radius is the primary signal.** The causal graph propagation — not the LLM, not the templates — drives the verdict.
2. **LLM is a contextual override.** It may upgrade or downgrade the verdict only with strong signals (`SAFE` or `BLOCK_REVIEW`).
3. **Failure templates are optional hypotheses.** They never drive verdict upgrades. The pipeline runs without them if the module is unavailable.
4. **Defensive LLM handling.** `_sanitize_llm_output` and `_normalize_failure_simulation` clean unicode-escape artifacts, stray quotes, and backfill required schema fields. LLM output is never trusted directly.
5. **Full-blob persistence.** The entire orchestrator result is dumped into `AnalysisRun.analysis_snapshot` as JSON. Structured tables above are pre-extracted, indexed projections.
6. **Repo-wide symbol index reuses fetched snapshots.** Zero extra HTTP calls — the index is built from data already fetched for the diff.
7. **Two execution paths.** Synchronous (API) and asynchronous (Dramatiq workers) share the same orchestrator and persistence logic.
8. **Graceful degradation.** Every optional module (failure templates, LLM, repo index) degrades to a fallback. The core blast-radius signal never depends on them.