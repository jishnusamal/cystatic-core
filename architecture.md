# Factor — Active System Architecture

## What Factor Does

Factor is a **blast-radius and refactor-risk analysis engine** for code changes. Given a PR (or raw diff), it determines which downstream services, endpoints, databases, and queues are impacted, assigns a confidence-weighted verdict, and posts a structured PR comment — all without requiring the reviewer to hold the full system in their head.

The core design principle: **evidence-based progressive compression drives the verdict; the LLM is an expert reviewer; failure scenarios are generated only from high-confidence hypotheses.**

---

## High-Level Flow

```
PR webhook / API request
  │
  ▼
InputPreparationPipeline        fetch diff + file snapshots (mode-dependent)
  │
  ▼
ChangeUnderstandingPipeline     analyze the change itself
  │
  ▼
EvidencePipeline                generate semantic evidence from all analyzers
  │
  ▼
InferencePipeline               progressive compression → hypotheses → scenarios
  │
  ▼
ReviewPipeline                  LLM review (optional) + verdict aggregation
  │
  ▼
Result                          PR comment + persisted run (Tortoise ORM → Postgres)
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
│   │
│   ├── pipelines/              modular pipeline implementations
│   │   ├── __init__.py         pipeline documentation
│   │   ├── input_preparation.py  InputPreparationPipeline
│   │   ├── change_understanding.py  ChangeUnderstandingPipeline
│   │   ├── evidence.py         EvidencePipeline
│   │   ├── inference.py        InferencePipeline
│   │   └── review.py           ReviewPipeline
│   │
│   ├── analysers/              semantic analyzers (10 analyzers)
│   │   ├── analysis_context.py     AnalysisContext
│   │   ├── base.py                 BaseAnalyzer
│   │   ├── business_object_analyzer.py
│   │   ├── business_objects.py
│   │   ├── cache_dependencies.py
│   │   ├── changed_symbols.py
│   │   ├── constraints.py
│   │   ├── database_relationships.py
│   │   ├── domain_hub.py
│   │   ├── domain_relationships.py
│   │   ├── endpoint_relationships.py
│   │   ├── event_relationships_analyzer.py
│   │   ├── event_relationships.py
│   │   ├── evidence_registry.py    EvidenceRegistry
│   │   ├── external_dependencies.py
│   │   ├── import_relationships.py
│   │   ├── naming_similarity.py
│   │   ├── operational_constraints.py
│   │   ├── ownership.py
│   │   ├── registry.py
│   │   ├── risk_anchors.py
│   │   ├── service_relationships.py
│   │   ├── side_effects.py
│   │   └── transaction_boundary.py
│   │
│   ├── evidence/               evidence compression pipeline
│   │   ├── compression_pipeline.py  CompressionPipeline (progressive compression)
│   │   ├── deduplicator.py          EvidenceDeduplicator
│   │   ├── clusterer.py             EvidenceClusterer
│   │   ├── scoring.py               EvidenceScorer
│   │   ├── causal_chain.py          CausalChainVerifier
│   │   └── pruner.py                EvidencePruner
│   │
│   ├── hypothesis/             hypothesis generation
│   │   ├── generator.py        HypothesisGenerator
│   │   ├── confidence.py       ConfidenceCalculator
│   │   └── confidence_aggregator.py
│   │
│   ├── models/                 Pydantic data models
│   │   ├── change_understanding.py  ChangeUnderstanding
│   │   ├── evidence_bundle.py       EvidenceBundle
│   │   ├── changed_symbol.py        ChangedSymbol
│   │   ├── risk_anchor.py           RiskAnchor
│   │   ├── impact_evidence.py       ImpactEvidence
│   │   ├── side_effect.py           SideEffect
│   │   ├── constraint.py            Constraint
│   │   ├── business_object.py       BusinessObject
│   │   ├── impact_hypothesis.py     ImpactHypothesis
│   │   ├── failure_scenario.py      FailureScenario
│   │   ├── entity_ref.py            EntityRef
│   │   └── enums.py                 Enumerations
│   │
│   ├── scenarios/              failure scenario generation
│   │   └── generator.py        FailureScenarioGenerator
│   │
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
│   ├── constraint_extractor.py extract_constraints
│   ├── constraint_types.py     ConstraintSet, ConstraintType, etc.
│   ├── change_influence.py     build_change_influence, extract_changed_symbols
│   ├── impact_evidence.py      build_impact_evidence
│   ├── llm_input_builder.py    build_llm_input (reviewer-ready facts)
│   ├── llm_packet_compressor.py RIRCompressor (legacy + v3)
│   ├── failure_templates.py    match_failure_templates (optional, lazy)
│   ├── failure_simulation_llm.py LLM-based failure simulation
│   ├── failure_simulator.py    rules-based fallback simulator
│   ├── scenario_validator.py   score_scenarios, ValidationScore
│   ├── file_exclusion.py       FileExclusionService
│   └── risk_compressor.py      compress_risk_hypotheses
│
├── language_adapters/          per-language static analysis
│   ├── python/python_adapter.py  Python adapter (DIFF_ONLY + FULL_FILE)
│   ├── ts_adapter.py            TypeScript adapter
│   └── interfaces/              adapter protocol definitions (WIP)
│
├── source_adapters/            source-control integration
│   ├── github/                 full GitHub integration
│   │   ├── github_client.py    fetch diffs, file snapshots, SHAs
│   │   ├── auth.py             installation auth, JWT, token exchange
│   │   ├── bot.py              post comments to PRs
│   │   ├── event_handler.py    dispatch webhook events to jobs
│   │   ├── comment_formatter.py render PR comments
│   │   └── webhook.py          webhook parsing + signature validation
│   └── gitlab/                 GitLab adapter (stub)
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
│   ├── core_engine_tests.py
│   ├── test_evidence_graph.py
│   ├── test_weak_edges.py
│   ├── test_shared_state_resource_model.py
│   ├── test_repo_symbol_index.py
│   ├── github_webhook_tests.py
│   ├── github_worker_tests.py
│   ├── language_adapter_tests.py
│   ├── source_adapter_tests.py
│   ├── test_evidence_driven_pipeline.py
│   ├── test_llm_packet_compressor.py
│   ├── test_risk_compressor.py
│   └── test_webhook.py
│
└── utils/
    └── unzip.py                archive extraction
```

---

## Pipeline Architecture (Active)

Factor uses a **5-stage modular pipeline architecture**. Each pipeline has a single responsibility and produces a well-defined output that becomes the input to the next stage.

### Pipeline Flow

```
InputPreparationPipeline
    ↓ produces: PreparedInputs
ChangeUnderstandingPipeline
    ↓ produces: ChangeUnderstanding
EvidencePipeline
    ↓ produces: EvidenceBundle
InferencePipeline
    ↓ produces: InferenceResult
ReviewPipeline
    ↓ produces: Review
```

### Orchestrator Coordination

The `BaseOrchestrator` coordinates pipeline execution using the **template method pattern**:

- **`Orchestrator`**: Production mode (FULL_FILE) — fetches diff + full file snapshots
- **`DiffOrchestrator`**: Demo/sandbox mode (DIFF_ONLY) — raw diff text only, no repo access

Both share the same 5-stage pipeline execution in `BaseOrchestrator.run_pr_analysis()`.

---

## Stage 1: InputPreparationPipeline

**File:** `core_engine/pipelines/input_preparation.py`

**Purpose:** Prepare analysis inputs based on the analysis mode (FULL_FILE vs DIFF_ONLY).

**Output:** `PreparedInputs` dataclass containing:
- `enriched_files`: List of enriched file data from the language adapter
- `diff_ir`: The diff IR from the source adapter
- `repo_index`: Optional repository symbol index (FULL_FILE mode only)
- `excluded_files`: List of files excluded from analysis

**Steps:**
1. Fetch diff from source adapter
2. Apply file exclusions (lockfiles, generated code, assets)
3. Extract changed files using language adapter
4. **FULL_FILE mode:**
   - Fetch full file snapshots at head SHA
   - Enrich files with functions, endpoints, keyword signals
   - Build `RepositorySymbolIndex` from snapshots
5. **DIFF_ONLY mode:**
   - Enrich files from diff hunks only
   - No repo access, no file snapshots

**Key Design:** Zero extra HTTP calls for repo index — reuses snapshots already fetched for the diff.

---

## Stage 2: ChangeUnderstandingPipeline

**File:** `core_engine/pipelines/change_understanding.py`

**Purpose:** Analyze the PR change itself — extract symbols, detect risks, build causal graph.

**Output:** `ChangeUnderstanding` model containing:
- `changed_symbols`: All symbols modified by the change
- `risk_anchors`: Changes known to increase downstream uncertainty
- `behavior_diffs`: Behavior-level deltas from the change
- `side_effects`: Side effects introduced or affected
- `constraints`: Constraints that apply to the change
- `business_objects`: Business objects referenced
- `enriched_files`: Enriched file data
- `risk_patterns`: Detected risk patterns
- `entry_points_affected`: Entry points affected by the change
- `causal_graph`: Causal graph built from the change
- `system_deltas`: System-level behavior deltas

**Steps:**
1. Detect risk patterns (`RiskPatternDetector`)
2. Resolve entry points (`EntryPointResolver`)
3. Extract behavior deltas and diffs
4. Classify reachability (`ReachabilityClassifier`)
5. Detect side effects (`SideEffectDetector`)
6. Extract constraints (`ConstraintExtractor`)
7. Extract changed symbols
8. Build causal graph (`build_causal_graph`)
9. Build impact evidence
10. Build change influence
11. Build system behavior deltas
12. Extract business objects from constraints

**Key Design:** This is the deterministic analysis core. All static analysis happens here before any semantic evidence generation.

---

## Stage 3: EvidencePipeline

**File:** `core_engine/pipelines/evidence.py`

**Purpose:** Generate semantic evidence from change understanding by running all analyzers.

**Output:** `EvidenceBundle` model containing:
- `changed_symbols`: All symbols modified by the change
- `risk_anchors`: Changes known to increase downstream uncertainty
- `impact_evidence`: Deterministic facts connecting entities
- `side_effects`: Side effects introduced or affected
- `constraints`: Constraints that apply to the change
- `business_objects`: Business objects referenced
- `domains`: Business domains touched by the change
- `confidence`: Overall confidence in this evidence bundle (0.0–1.0)

**Steps:**
1. Extract changed symbols and risk anchors from change understanding
2. Build `AnalysisContext` (enriched files + risk patterns)
3. Create `EvidenceRegistry`
4. Run all 10 semantic analyzers:
   - `DomainHubAnalyzer` — domain boundaries and hubs
   - `BusinessObjectAnalyzer` — business object relationships
   - `TransactionBoundaryAnalyzer` — transaction boundaries
   - `DatabaseRelationshipAnalyzer` — database relationships
   - `EventRelationshipAnalyzer` — event-driven relationships
   - `OperationalConstraintAnalyzer` — operational constraints
   - `ServiceRelationshipAnalyzer` — service-to-service relationships
   - `CacheDependencyAnalyzer` — cache dependencies
   - `ExternalDependencyAnalyzer` — external API dependencies
   - `OwnershipAnalyzer` — code ownership
5. Build initial evidence bundle from registry
6. Build final evidence bundle with all data

**Key Design:** The EvidencePipeline owns ALL evidence generation. The orchestrator doesn't even know analyzers exist. Each analyzer is independent and gracefully degrades on failure.

---

## Stage 4: InferencePipeline

**File:** `core_engine/pipelines/inference.py`

**Purpose:** Generate hypotheses and scenarios from evidence using progressive compression.

**Output:** `InferenceResult` containing:
- `hypotheses`: Generated impact hypotheses (merged, ranked)
- `scenarios`: Generated failure scenarios (high-confidence only)
- `evidence_clusters`: Aggregated and pruned evidence clusters
- `compression`: Compression statistics from the pipeline

**Progressive Compression Pipeline:**

```
Changed Symbols → Raw Evidence → Deduplicate → Evidence Clusters
→ Score + Causal Chain Check → Prune → Candidate Hypotheses
→ Merge → Rank + Filter → Failure Scenarios → Review → Verdict
```

**Steps:**
1. **Deduplicate** equivalent evidence items
2. **Cluster** by business object / domain / flow
3. **Score** each cluster (confidence, impact, reachability)
4. **Verify causal chains** (are the connections valid?)
5. **Prune** low-quality clusters (configurable thresholds)
6. **Generate hypotheses** (one per cluster)
7. **Merge** similar hypotheses
8. **Select high-confidence hypotheses** for simulation (threshold: 0.60)
9. **Generate failure scenarios** ONLY from high-confidence hypotheses

**Key Design:** Progressive compression reduces thousands of evidence items into a small number of high-confidence scenarios. The pipeline never discards evidence outright — it compresses it.

**Compression Statistics Tracked:**
- Raw evidence count
- Deduplicated group count
- Cluster count
- Pruned cluster count
- Hypothesis count
- Merged hypothesis count
- Simulation count
- Compression ratio

---

## Stage 5: ReviewPipeline

**File:** `core_engine/pipelines/review.py`

**Purpose:** Perform LLM review (optional) and aggregate final verdict.

**Output:** `Review` containing:
- `failure_simulation`: LLM-generated review output (or deterministic fallback)
- `validation_score`: Scenario validation scores
- `verdict`: Aggregated verdict (APPROVE, REVIEW_REQUIRED, BLOCK)

**Architecture:**
```
Deterministic engine → llm_input_builder → LLM (expert reviewer) → Review
```

The LLM never sees internal implementation artifacts — only reviewer-ready facts.

**Steps:**
1. Run inference pipeline to generate deterministic scenarios
2. Build reviewer-ready facts for the LLM (`llm_input_builder`)
3. **Run LLM if available:**
   - Call LLM with reviewer-ready facts
   - Sanitize LLM output (defensive parsing)
4. **If no LLM:** Build review output from deterministic scenarios
5. Apply deterministic validation scores (`score_scenarios`)
6. Aggregate verdict from LLM output and risk patterns

**Verdict Aggregation Logic:**
1. Accept LLM verdict if present
2. Fall back to risk pattern-based verdict:
   - HIGH severity → BLOCK
   - MEDIUM/LOW severity → REVIEW_REQUIRED
   - No risk patterns → APPROVE

**LLM Output Format (Reviewer-Ready):**
```json
{
  "verdict": "BLOCK" | "REVIEW_REQUIRED" | "APPROVE",
  "executive_summary": "High-level summary of the risk",
  "primary_concern": {
    "title": "Main concern title",
    "why_blocking": "Why this blocks the PR",
    "execution_path": "How this could happen in production",
    "customer_or_business_impact": "Business impact",
    "why_existing_tests_miss_it": "Test coverage gap",
    "confidence_rationale": "Why we're confident",
    "required_validation": "What tests are needed"
  },
  "additional_observations": [...],
  "required_tests": [...],
  "reviewer_questions": [...],
  "merge_recommendation": "Safe to merge / Requires review / Blocked by..."
}
```

**Key Design:** The LLM is an expert reviewer, not a signal generator. It writes an engineering review from deterministic findings. Defensive LLM handling sanitizes unicode-escape artifacts, stray quotes, and backfills required schema fields.

---

## Data Models

### ChangeUnderstanding

**File:** `core_engine/models/change_understanding.py`

The output of ChangeUnderstandingPipeline and input to EvidencePipeline. Contains all deterministic analysis of the change itself.

**Fields:**
- `changed_symbols`: All symbols modified by the change
- `risk_anchors`: Changes known to increase downstream uncertainty
- `behavior_diffs`: Behavior-level deltas from the change
- `side_effects`: Side effects introduced or affected
- `constraints`: Constraints that apply to the change
- `business_objects`: Business objects referenced
- `enriched_files`: Enriched file data from the analysis
- `risk_patterns`: Detected risk patterns
- `entry_points_affected`: Entry points affected by the change
- `causal_graph`: Causal graph built from the change
- `system_deltas`: System-level behavior deltas

### EvidenceBundle

**File:** `core_engine/models/evidence_bundle.py`

The single semantic representation consumed by downstream reasoning (hypothesis generation, scenario construction). Replaces propagation output as the primary reasoning input.

**Fields:**
- `changed_symbols`: All symbols modified by the change
- `risk_anchors`: Changes known to increase downstream uncertainty
- `impact_evidence`: Deterministic facts connecting entities
- `side_effects`: Side effects introduced or affected
- `constraints`: Constraints that apply to the change
- `business_objects`: Business objects referenced
- `domains`: Business domains touched by the change
- `confidence`: Overall confidence in this evidence bundle (0.0–1.0)

### InferenceResult

**File:** `core_engine/pipelines/inference.py`

The output of InferencePipeline containing compressed evidence and generated scenarios.

**Fields:**
- `hypotheses`: Generated impact hypotheses (merged, ranked)
- `scenarios`: Generated failure scenarios (high-confidence only)
- `evidence_clusters`: Aggregated and pruned evidence clusters
- `compression`: Compression statistics from the pipeline

### Review

**File:** `core_engine/pipelines/review.py`

The output of ReviewPipeline containing the final verdict.

**Fields:**
- `failure_simulation`: LLM-generated review output (or deterministic fallback)
- `validation_score`: Scenario validation scores
- `verdict`: Aggregated verdict (APPROVE, REVIEW_REQUIRED, BLOCK)

---

## Semantic Analyzers (EvidencePipeline)

The EvidencePipeline runs 10 independent semantic analyzers, each contributing to the EvidenceBundle:

### 1. DomainHubAnalyzer
**File:** `core_engine/analysers/domain_hub.py`

Identifies domain boundaries and hub symbols that connect multiple domains. Detects when changes touch shared domain hubs that could have cross-domain impact.

### 2. BusinessObjectAnalyzer
**File:** `core_engine/analysers/business_object_analyzer.py`

Analyzes business object relationships and dependencies. Identifies critical business objects (e.g., Payment, Order, User) and their relationships.

### 3. TransactionBoundaryAnalyzer
**File:** `core_engine/analysers/transaction_boundary.py`

Detects transaction boundaries and potential transaction-related risks (e.g., missing rollbacks, distributed transaction issues).

### 4. DatabaseRelationshipAnalyzer
**File:** `core_engine/analysers/database_relationships.py`

Maps database relationships and dependencies. Identifies which tables/collections are affected by the change and their relationships.

### 5. EventRelationshipAnalyzer
**File:** `core_engine/analysers/event_relationships_analyzer.py`

Analyzes event-driven relationships in the codebase. Detects event producers, consumers, and potential event schema changes.

### 6. OperationalConstraintAnalyzer
**File:** `core_engine/analysers/operational_constraints.py`

Identifies operational constraints (e.g., rate limits, circuit breakers, retry policies) that may be affected by the change.

### 7. ServiceRelationshipAnalyzer
**File:** `core_engine/analysers/service_relationships.py`

Maps service-to-service relationships and dependencies. Identifies which services call which, and potential impact chains.

### 8. CacheDependencyAnalyzer
**File:** `core_engine/analysers/cache_dependencies.py`

Analyzes cache dependencies and invalidation patterns. Detects cache keys, TTLs, and potential cache-related issues.

### 9. ExternalDependencyAnalyzer
**File:** `core_engine/analysers/external_dependencies.py`

Identifies external API dependencies and integrations. Maps external service calls and potential failure modes.

### 10. OwnershipAnalyzer
**File:** `core_engine/analysers/ownership.py`

Analyzes code ownership and team boundaries. Identifies which teams own which components for review routing.

**Analyzer Output:** Each analyzer produces structured output that is ingested by the `EvidenceRegistry` and aggregated into the `EvidenceBundle`.

---

## Evidence Compression Pipeline

**File:** `core_engine/evidence/compression_pipeline.py`

The progressive compression pipeline is the core inference mechanism. It transforms thousands of raw evidence items into a small number of high-confidence hypotheses and scenarios.

### Compression Stages

```
1. Raw Evidence (thousands of items)
   ↓ Deduplicate
2. Deduplicated Groups (hundreds of groups)
   ↓ Cluster
3. Evidence Clusters (tens of clusters)
   ↓ Score + Causal Chain Verification
4. Scored Clusters (filtered by confidence)
   ↓ Prune
5. Pruned Clusters (high-quality only)
   ↓ Generate Hypotheses
6. Candidate Hypotheses (one per cluster)
   ↓ Merge
7. Merged Hypotheses (deduplicated)
   ↓ Rank + Filter
8. Ranked Hypotheses (sorted by confidence)
   ↓ Select for Simulation
9. Simulation Candidates (high-confidence only, threshold: 0.60)
   ↓ Generate Scenarios
10. Failure Scenarios (testable claims)
```

### Key Components

**EvidenceDeduplicator** (`core_engine/evidence/deduplicator.py`)
- Groups equivalent evidence items
- Reduces redundancy in the evidence set

**EvidenceClusterer** (`core_engine/evidence/clusterer.py`)
- Clusters evidence by business object, domain, or flow
- Creates semantic groups of related evidence

**EvidenceScorer** (`core_engine/evidence/scoring.py`)
- Scores each cluster based on:
  - Confidence (how certain are we?)
  - Impact (how severe is the potential issue?)
  - Reachability (how many systems are affected?)

**CausalChainVerifier** (`core_engine/evidence/causal_chain.py`)
- Verifies that causal chains in evidence are valid
- Ensures impact paths are logically sound

**EvidencePruner** (`core_engine/evidence/pruner.py`)
- Prunes low-quality clusters based on configurable thresholds
- Configurable via `PruningConfig`:
  - `min_confidence`: Minimum confidence threshold (default: 0.3)
  - `min_impact`: Minimum impact score (default: 0.2)
  - `min_reachability`: Minimum reachability score (default: 0.1)
  - `simulation_confidence_threshold`: Threshold for simulation (default: 0.60)

**HypothesisGenerator** (`core_engine/hypothesis/generator.py`)
- Generates one hypothesis per cluster
- Hypotheses are testable claims about potential impact

**FailureScenarioGenerator** (`core_engine/scenarios/generator.py`)
- Generates failure scenarios ONLY from high-confidence hypotheses
- Scenarios are concrete, testable failure modes

---

## Language Adapters

**Directory:** `language_adapters/`

Language adapters perform per-language static analysis to extract changed files, functions, endpoints, and signals from diffs.

### Python Adapter

**File:** `language_adapters/python/python_adapter.py`

**Capabilities:**
- `extract_changed_files()`: Extract changed files from diff IR
- `extract_changed_functions()`: Extract changed functions (FULL_FILE + DIFF_ONLY modes)
- `extract_endpoints()`: Extract FastAPI, Flask, Django endpoints
- `extract_keyword_signals_from_diff()`: Extract keyword signals from diff

**Modes:**
- `FULL_FILE`: Uses AST analysis on full file snapshots
- `DIFF_ONLY`: Uses regex/heuristic analysis on diff hunks only

### TypeScript Adapter

**File:** `language_adapters/ts_adapter.py`

TypeScript equivalent of the Python adapter. Uses regex/heuristic-based analysis.

**Key Design:** Both adapters produce `enriched_files` dicts consumed by the core engine. The adapters are language-specific but produce a language-agnostic output format.

---

## Source Adapters

**Directory:** `source_adapters/`

Source adapters integrate with source control systems to fetch diffs, file snapshots, and PR metadata.

### GitHub Integration

**Directory:** `source_adapters/github/`

**Components:**
- **`github_client.py`**: Fetches diffs, file snapshots, SHAs from GitHub API
- **`auth.py`**: Handles installation auth, JWT, token exchange
- **`bot.py`**: Posts comments to PRs
- **`event_handler.py`**: Dispatches webhook events to jobs
- **`comment_formatter.py`**: Renders PR comments
- **`webhook.py`**: Parses webhooks + signature validation

**Capabilities:**
- Fetch PR diff
- Fetch file snapshots at specific SHA
- Post PR comments
- Handle webhook events
- Authenticate with GitHub App installation

### GitLab Adapter

**Directory:** `source_adapters/gitlab/`

**Status:** Stub — `fetch_not_implemented` placeholder for future work.

---

## API Layer

**Directory:** `api/`

**Framework:** FastAPI + Uvicorn/Gunicorn

**ORM:** Tortoise ORM on asyncpg (Neon Postgres)

**Entrypoint:** `api/main.py` (uvicorn api.main:app)

**Routers:**
- `api/admin/urls.py`: Admin API routes
- `api/user/urls.py`: User-facing API routes

**Configuration:**
- `api/settings.py`: pydantic-settings configuration
- `api/db.py`: Tortoise config (runtime, pooled Neon URL)
- `api/db_migrations.py`: Aerich migration config (direct Neon URL)

**Key Design:** Schema generation is disabled at runtime (`generate_schemas=False`).

---

## Data Persistence (Tortoise ORM → Postgres)

**File:** `api/models.py`

11 runtime tables + 1 eval-harness table:

| Table | Purpose |
|-------|---------|
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

**Persistence Flow:** `Orchestrator.log_run()` → `persist_analysis_result()` writes all 11 tables in a single call. The entire orchestrator result dict is also dumped into `AnalysisRun.analysis_snapshot` as JSON — nothing is lost.

---

## Workers & Queue

**Directory:** `workers/`

**Broker:** Dramatiq on Redis (`workers/queue.py`)

**URL Resolution:**
- `REDIS_URL` → derived `rediss://` from `UPSTASH_REDIS_REST_*` → `localhost`

**Worker:** `workers/analyze_pr.py`
- Receives a job
- Runs `Orchestrator.run_pr_analysis()`
- Posts the comment
- Persists the result

**Deduplication:**
- `delivery_id` on both `AnalysisRun` and `AnalysisJob` prevents double-runs on webhook retries
- `AnalysisJob.idempotency_key` is unique

---

## Observability

**Directory:** `instrumentation/sentry/`

**Sentry Integration:**
- Middleware attached to the FastAPI app (`instrumentation/sentry/sentry.py`)
- Per-request context helpers (`instrumentation/sentry/contexts.py`) attach:
  - Repository
  - PR number
  - Analysis run ID
  - Other relevant context to Sentry events

---

## PR Comment

**Template:** `templates/github/pr_comment.md.j2`

**Rendering:** `_render_pr_comment()` in `BaseOrchestrator`

**Variables:**
- `verdict`: Final verdict (APPROVE, REVIEW_REQUIRED, BLOCK)
- `failure_simulation`: Normalized LLM output (or deterministic fallback)
- Full analysis result

**Storage:** Rendered comment body is stored in `analysis_comments.body` and linked back to the run via `AnalysisRun.canonical_comment`.

---

## Key Design Decisions

1. **Evidence-based progressive compression.** The compression pipeline — not the LLM, not causal graph propagation alone — drives the verdict. Thousands of evidence items are compressed into high-confidence scenarios.

2. **LLM is an expert reviewer.** It writes an engineering review from deterministic findings. It never sees internal implementation artifacts — only reviewer-ready facts from `llm_input_builder`.

3. **5-stage modular pipeline.** Each pipeline has a single responsibility. The orchestrator coordinates but doesn't implement analysis logic.

4. **10 independent semantic analyzers.** Each analyzer is independent and gracefully degrades on failure. The EvidencePipeline owns ALL evidence generation.

5. **Defensive LLM handling.** `_sanitize_llm_output` and `_normalize_failure_simulation` clean unicode-escape artifacts, stray quotes, and backfill required schema fields. LLM output is never trusted directly.

6. **Full-blob persistence.** The entire orchestrator result is dumped into `AnalysisRun.analysis_snapshot` as JSON. Structured tables are pre-extracted, indexed projections.

7. **Two execution paths.** Synchronous (API) and asynchronous (Dramatiq workers) share the same orchestrator and pipeline logic.

8. **Graceful degradation.** Every optional module (LLM, analyzers, compression stages) degrades to a fallback. The core evidence-based signal never depends on them.

9. **Zero extra HTTP calls for repo index.** The repository symbol index is built from snapshots already fetched for the diff.

10. **Progressive compression never discards evidence.** It compresses evidence into clusters, hypotheses, and scenarios. Nothing is lost — it's just aggregated.

---

## Active vs. Legacy Components

### Active (Current) Architecture

The active architecture uses the **5-stage pipeline**:

1. **InputPreparationPipeline** — mode-dependent input preparation
2. **ChangeUnderstandingPipeline** — deterministic change analysis
3. **EvidencePipeline** — semantic evidence generation (10 analyzers)
4. **InferencePipeline** — progressive compression → hypotheses → scenarios
5. **ReviewPipeline** — LLM review + verdict aggregation

**Key Models:**
- `ChangeUnderstanding` — output of stage 2
- `EvidenceBundle` — output of stage 3, input to stage 4
- `InferenceResult` — output of stage 4
- `Review` — output of stage 5

### Legacy Components (Still Present but Not Primary)

The following components exist in the codebase but are not part of the primary pipeline flow:

- **`causal_graph.py`** — Legacy causal graph implementation (still used in ChangeUnderstandingPipeline)
- **`propagation_engine.py`** — Legacy propagation engine (not used in primary pipeline)
- **`llm_packet_compressor.py`** — Legacy IR compression (replaced by evidence compression pipeline)
- **`failure_templates.py`** — Optional failure template matching (lazy-loaded, not core)
- **`failure_simulation_llm.py`** — Legacy LLM simulation (replaced by ReviewPipeline)
- **`failure_simulator.py`** — Rules-based fallback (replaced by deterministic scenarios)
- **`scenario_validator.py`** — Used in ReviewPipeline for validation scoring
- **`rir_compressor.py`** — Legacy compressor (not used in primary pipeline)

**Migration Path:** The legacy components are being phased out in favor of the evidence-based pipeline. They remain in the codebase for backward compatibility but are not part of the primary execution path.

---

## Testing

**Directory:** `tests/`

**Test Files:**
- `core_engine_tests.py` — causal graph + propagation (legacy)
- `test_evidence_driven_pipeline.py` — evidence-driven pipeline (active)
- `test_evidence_graph.py` — evidence graph construction
- `test_weak_edges.py` — weak edge detection
- `test_shared_state_resource_model.py` — shared-state coupling
- `test_repo_symbol_index.py` — repo-wide symbol index
- `test_llm_packet_compressor.py` — legacy compressor tests
- `test_risk_compressor.py` — risk compression tests
- `github_webhook_tests.py` — webhook parsing + dispatch
- `github_worker_tests.py` — worker + orchestrator integration
- `language_adapter_tests.py` — language adapter tests
- `source_adapter_tests.py` — source adapter tests
- `test_webhook.py` — webhook tests
- `test_constraint_extractor.py` — constraint extraction tests

**Test Strategy:** Run the narrowest possible test. Preferred order:
1. Single failing test
2. Relevant test file
3. Relevant test suite
4. Full test suite only when necessary

---

## Configuration

**File:** `pyproject.toml`, `requirements.txt`, `pylock.toml`

**Key Dependencies:**
- FastAPI + Uvicorn/Gunicorn (API layer)
- Tortoise ORM + asyncpg (database)
- Dramatiq + Redis (queue)
- Pydantic (data models)
- Jinja2 (template rendering)
- OpenAI API (LLM, optional)
- Sentry (observability)

**Settings:** `api/settings.py` (pydantic-settings)

---

## Summary

Factor's active architecture is a **5-stage evidence-based pipeline** that progressively compresses thousands of evidence items into high-confidence failure scenarios. The LLM acts as an expert reviewer, not a signal generator. The system is designed for graceful degradation — every optional component can fail without breaking the core analysis.

**The pipeline never discards evidence — it compresses it.** This ensures that no potential risk is lost during analysis, even if it doesn't make it to the final scenarios.